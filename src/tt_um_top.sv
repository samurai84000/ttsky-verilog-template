module tt_um_top (
    input  logic [7:0] ui_in,    // Dedicated inputs
    output logic [7:0] uo_out,   // Dedicated outputs
    input  logic [7:0] uio_in,   // IOs: Input path
    output logic [7:0] uio_out,  // IOs: Output path
    output logic [7:0] uio_oe,   // IOs: Enable path (active high: 0=input, 1=output)
    input  logic       ena,      // always 1 when the design is powered
    input  logic       clk,      // clock
    input  logic       rst_n     // reset_n - low to reset
);

    // 1. Reset Logic: Invert the active-low rst_n
    logic rst;
    assign rst = !rst_n;

    // 2. Mapping the 12-bit ADC Data
    logic [11:0] combined_adc_data;
    assign combined_adc_data = {uio_in[7:0], ui_in[7:4]};

    // 3. Bidirectional Pin Configuration
    // uio[0] and uio[1] are outputs for ana_ctrl. uio[7:2] are inputs for ADC.
    assign uio_oe = 8'b00000011; 
    assign uio_out[7:2] = 6'b000000; 

    top user_project (
        .clk(clk),
        .rst(rst),
        .wakeup(ui_in[1]),
        .adc_EOC(ui_in[2]),
        .MISO(ui_in[3]),
        .adc_data(combined_adc_data),
        .spi_clk(uo_out[0]),
        .MOSI(uo_out[1]),
        .FRAM_cs(uo_out[2]),
        .LoRA_cs(uo_out[3]),
        .adc_conv_start(uo_out[4]),
        .en_sensor_vcc(uo_out[5]),
        .en_radio_vcc(uo_out[6]),
        // Fix: Map the 3-bit bus to the available pins
        .ana_ctrl({uio_out[1], uio_out[0], uo_out[7]}) 
    );

endmodule
