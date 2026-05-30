import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, Timer

# Helper coroutine to simulate the external ADC behavior
async def simulate_adc_handshake(dut, mock_value):
    """
    Watches for the FSM to request an ADC conversion, waits a few cycles
    to simulate hardware latency, provides data, and asserts End of Conversion (EOC).
    """
    # 1. Wait until the FSM drives adc_conv_start high
    while d_start := dut.adc_conv_start.value != 1:
        await RisingEdge(dut.clk)
    
    dut._log.info(f"[ADC Mock] Conversion requested! Feeding data: 0x{mock_value:03X}")
    
    # 2. Simulate standard ADC conversion delay (e.g., 5 clock cycles)
    for _ in range(5):
        await RisingEdge(dut.clk)
        
    # 3. Present the parallel data and assert End of Conversion (EOC)
    dut.adc_data.value = mock_value
    dut.adc_EOC.value = 1
    
    # 4. Hold EOC high for one clock cycle
    await RisingEdge(dut.clk)
    dut.adc_EOC.value = 0
    dut.adc_data.value = 0 # Clear data bus

@cocotb.test()
async def test_power_cycle_profile(dut):
    """
    Test suite mimicking a complete environment monitoring wake/sleep cycle
    to generate realistic VCD tracking logs for OpenROAD power analysis.
    """
    
    # --- STEP 1: Start the System Clock ---
    # Generates a 10MHz clock (period of 100 ns)
    clock = Clock(dut.clk, 100, units="ns")
    cocotb.start_soon(clock.start())
    
    # --- STEP 2: System Initialization and Reset ---
    dut._log.info("Driving system reset...")
    dut.rst.value = 1
    dut.wakeup.value = 0
    dut.adc_EOC.value = 0
    dut.adc_data.value = 0
    dut.MISO.value = 0
    
    # Hold reset for 5 clock cycles, then drop it
    for _ in range(5):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    
    # Verify we hit the ST_SHUTDOWN state (rails should be off)
    assert dut.en_sensor_vcc.value == 0, "Sensor rail active during shutdown!"
    assert dut.en_radio_vcc.value == 0, "Radio rail active during shutdown!"
    dut._log.info("System successfully entered low-power ST_SHUTDOWN state.")
    
    # Let the design idle in sleep mode for a brief period
    for _ in range(10):
        await RisingEdge(dut.clk)

    # --- STEP 3: Trigger Wakeup Pulse ---
    dut._log.info("Asserting wakeup signal...")
    dut.wakeup.value = 1
    await RisingEdge(dut.clk)
    dut.wakeup.value = 0 # FSM should register edge, clear wakeup input
    
    # --- STEP 4: Handle Sequence of ADC Reads ---
    # According to your FSM, it sweeps through multiple analog sensors.
    # We will spin off multiple ADC responses in order.
    
    # 1. Temperature Read (e.g., normal ambient)
    await simulate_adc_handshake(dut, mock_value=0x700)
    
    # 2. Soil Moisture Read
    await simulate_adc_handshake(dut, mock_value=0x500)
    
    # 3. Solar Current Read (Feed high solar data to clear SUNNY_THRESH=0x800)
    # This guarantees the FSM attempts a LoRA network buffer fill/transmission
    await simulate_adc_handshake(dut, mock_value=0x950)
    
    # 4. Solar Voltage Read
    await simulate_adc_handshake(dut, mock_value=0x600)
    
    # 5. Battery Voltage Read (Feed safe voltage above VBAT_CRIT)
    await simulate_adc_handshake(dut, mock_value=0x550)

    # --- STEP 5: Monitor SPI and Transmission Window ---
    dut._log.info("ADC sampling window complete. Tracking FSM storage behavior...")
    
    # Monitor for a frame window to ensure SPI master is generating clock pulses
    # We'll watch the lines execute for 200 clock cycles
    for cycle in range(200):
        await RisingEdge(dut.clk)
        
        # Monitor power gates turning on
        if dut.en_radio_vcc.value == 1 and cycle % 20 == 0:
            dut._log.info(f"Cycle {cycle}: LoRA Radio rail energized for buffer compilation.")
            
        # Optional: Feed mock data over SPI MISO if your FSM reads back data bytes
        if dut.FRAM_cs.value == 0 or dut.LoRA_cs.value == 0:
            # Simple loopback test: mirror MOSI bits back into MISO
            dut.MISO.value = dut.MOSI.value

    # --- STEP 6: Return to Low-Power Safe State ---
    dut._log.info("Execution profile complete. Waiting for safe return to shutdown...")
    
    # Give the FSM ample cycles to finish writing and settle back down
    timeout = 100
    while timeout > 0:
        await RisingEdge(dut.clk)
        if dut.en_sensor_vcc.value == 0 and dut.en_radio_vcc.value == 0:
            dut._log.info("Success! Rails isolated. FSM returned safely to low-power rest state.")
            break
        timeout -= 1
        
    if timeout == 0:
        dut._log.warning("Timeout reached before system fully power-gated.")
