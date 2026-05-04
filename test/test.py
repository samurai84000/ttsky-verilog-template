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

    # Reset
    dut._log.info("Reset")
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1

    dut._log.info("Test project behavior")

    # Wait for a few cycles for the FSM to settle after reset
    await ClockCycles(dut.clk, 5)

    # UPDATED ASSERTION:
    # We check that the SPI Chip Selects (uo_out[2] and uo_out[3]) are high (1) by default.
    # From your info.yaml: uo_out[2] is FRAM_cs, uo_out[3] is LoRA_cs.[cite: 3]
    # Binary 00001100 is 0x0C in hex.[cite: 4]
    uo_out_val = dut.uo_out.value
    dut._log.info(f"uo_out value is: {uo_out_val}")
    
    # This checks if bits 2 and 3 are set to 1
    assert (uo_out_val & 0x0C) == 0x0C 

    dut._log.info("Test passed: Chip Selects are inactive high.")
