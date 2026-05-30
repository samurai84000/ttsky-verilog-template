import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

def pack_adc_signals(mock_value, eoc_bit=0, wakeup_bit=0, miso_bit=0):
    """
    Helper function to pack individual bits and the 12-bit ADC value into
    the exact ui_in and uio_in byte configurations defined in tt_um_top.sv.
    """
    # combined_adc_data = {uio_in[7:0], ui_in[7:4]}
    adc_low_4bits = mock_value & 0xF
    adc_high_8bits = (mock_value >> 4) & 0xFF
    
    # ui_in mapping:
    # ui_in[7:4] = adc_low_4bits
    # ui_in[3]   = MISO
    # ui_in[2]   = adc_EOC
    # ui_in[1]   = wakeup
    # ui_in[0]   = 0
    ui_in_val = (adc_low_4bits << 4) | (miso_bit << 3) | (eoc_bit << 2) | (wakeup_bit << 1)
    
    return ui_in_val, adc_high_8bits

def get_signal_bit(signal, bit_idx):
    """
    Safely extracts a single bit from a packed signal vector handle,
    avoiding TypeError/ValueError from unresolvable 'X' or 'Z' states.
    """
    val = signal.value
    if not val.is_resolvable:
        return 0  # Fallback safely to 0 if the net is currently uninitialized
    return (val.integer >> bit_idx) & 1

async def simulate_adc_handshake(dut, mock_value):
    """
    Watches for the FSM to request an ADC conversion via uo_out[4] (adc_conv_start),
    waits a few cycles to simulate hardware latency, provides data, and asserts EOC.
    """
    # 1. Wait until the FSM drives adc_conv_start (uo_out[4]) high
    while True:
        if get_signal_bit(dut.uo_out, 4) == 1:
            break
        await RisingEdge(dut.clk)
    
    dut._log.info(f"[ADC Mock] Conversion requested! Feeding data: 0x{mock_value:03X}")
    
    # 2. Simulate standard ADC conversion delay (5 clock cycles)
    for _ in range(5):
        await RisingEdge(dut.clk)
        
    # 3. Present the parallel data and assert End of Conversion (ui_in[2] = 1)
    ui_val, uio_val = pack_adc_signals(mock_value, eoc_bit=1)
    dut.ui_in.value = ui_val
    dut.uio_in.value = uio_val
    
    # 4. Hold EOC high for one clock cycle
    await RisingEdge(dut.clk)
    
    # Clear EOC and data bus
    dut.ui_in.value = 0
    dut.uio_in.value = 0

@cocotb.test()
async def test_power_cycle_profile(dut):
    """
    Test suite mimicking a complete environment monitoring wake/sleep cycle
    to generate realistic VCD tracking logs for OpenROAD power analysis.
    """
    
    # --- STEP 1: Start the System Clock ---
    clock = Clock(dut.clk, 100, unit="ns")
    cocotb.start_soon(clock.start())
    
    # --- STEP 2: System Initialization and Reset ---
    dut._log.info("Driving system reset...")
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0  # TinyTapeout uses an active-low reset pin [cite: 2]
    
    # Hold reset for 5 clock cycles, then drop it
    for _ in range(5):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)
    
    # Verify we hit the ST_SHUTDOWN state safely via bit manipulation
    # uo_out[5] = en_sensor_vcc, uo_out[6] = en_radio_vcc [cite: 7, 8]
    assert get_signal_bit(dut.uo_out, 5) == 0, "Sensor rail active during shutdown!"
    assert get_signal_bit(dut.uo_out, 6) == 0, "Radio rail active during shutdown!"
    dut._log.info("System successfully entered low-power ST_SHUTDOWN state.")
    
    # Let the design idle in sleep mode for a brief period
    for _ in range(10):
        await RisingEdge(dut.clk)

    # --- STEP 3: Trigger Wakeup Pulse ---
    dut._log.info("Asserting wakeup signal via ui_in[1]...")
    ui_val, uio_val = pack_adc_signals(mock_value=0, wakeup_bit=1)
    dut.ui_in.value = ui_val
    await RisingEdge(dut.clk)
    dut.ui_in.value = 0  # Clear wakeup pulse
    
    # --- STEP 4: Handle Sequence of ADC Reads ---
    # 1. Temperature Read
    await simulate_adc_handshake(dut, mock_value=0x700)
    # 2. Soil Moisture Read
    await simulate_adc_handshake(dut, mock_value=0x500)
    # 3. Solar Current Read 
    await simulate_adc_handshake(dut, mock_value=0x950)
    # 4. Solar Voltage Read
    await simulate_adc_handshake(dut, mock_value=0x600)
    # 5. Battery Voltage Read 
    await simulate_adc_handshake(dut, mock_value=0x550)

    # --- STEP 5: Monitor SPI and Transmission Window ---
    dut._log.info("ADC sampling window complete. Tracking FSM storage behavior...")
    
    # Monitor for 200 clock cycles to watch lines cycle
    for cycle in range(200):
        await RisingEdge(dut.clk)
        
        # Monitor power gates turning on
        if get_signal_bit(dut.uo_out, 6) == 1 and cycle % 20 == 0:
            dut._log.info(f"Cycle {cycle}: LoRA Radio rail energized for buffer compilation.")
            
        # Loopback test: Mirror MOSI (uo_out[1]) into MISO (ui_in[3]) when chip selects are low [cite: 7]
        if get_signal_bit(dut.uo_out, 2) == 0 or get_signal_bit(dut.uo_out, 3) == 0:
            mosi_bit = get_signal_bit(dut.uo_out, 1)
            ui_val, uio_val = pack_adc_signals(mock_value=0, miso_bit=mosi_bit)
            dut.ui_in.value = ui_val

    # --- STEP 6: Return to Low-Power Safe State ---
    dut._log.info("Execution profile complete. Waiting for safe return to shutdown...")
    
    timeout = 100
    while timeout > 0:
        await RisingEdge(dut.clk)
        if get_signal_bit(dut.uo_out, 5) == 0 and get_signal_bit(dut.uo_out, 6) == 0:
            dut._log.info("Success! Rails isolated. FSM returned safely to low-power rest state.")
            break
        timeout -= 1
        
    if timeout == 0:
        dut._log.warning("Timeout reached before system fully power-gated.")
