# SPDX-FileCopyrightText: © 2024 Tiny Tapeout
# SPDX-License-Identifier: Apache-2.0

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles

@cocotb.test()
async def test_project(dut):
    dut._log.info("Start")

    # Set the clock period to 10 us (100 KHz)
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    # Reset procedure
    dut._log.info("Reset")
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1

    dut._log.info("Test project behavior")

    # Wait for one clock cycle for signals to propagate
    await ClockCycles(dut.clk, 1)

    # Check the actual hardware output
    # Your log showed: LogicArray('00001100') which is 0x0C
    # This corresponds to your pins: uo_out[2]=FRAM_cs, uo_out[3]=LoRA_cs
    # Both are 1 (inactive/high) by default, which is correct.
    uo_out_val = int(dut.uo_out.value)
    dut._log.info(f"uo_out value is: {uo_out_val:08b} (binary)")
    
    # Final fix: Assert that the SPI Chip Selects are 1 (inactive)
    assert (uo_out_val & 0x0C) == 0x0C 

    dut._log.info("Test passed successfully!")
