module top (
    input  logic rst, clk, wakeup,
    input  logic adc_EOC,
    input  logic [11:0] adc_data,
    output logic adc_conv_start,
    output logic [2:0] ana_ctrl,
    output logic en_sensor_vcc, en_radio_vcc,
    
    // Physical SPI Pins
    output logic spi_clk, MOSI, FRAM_cs, LoRA_cs,
    input  logic MISO
);

    // --- Internal Handshake Wires ---
    logic [7:0] spi_tx_byte, spi_rx_byte;
    logic spi_start, spi_done, master_cs;

    // --- Instantiate FSM (The Controller) ---
    FSM fsm_inst (
        .rst(rst), .clk(clk), .wakeup(wakeup),
        .adc_EOC(adc_EOC), .adc_data(adc_data),
        .adc_conv_start(adc_conv_start), .ana_ctrl(ana_ctrl),
        .en_sensor_vcc(en_sensor_vcc), .en_radio_vcc(en_radio_vcc),
        .FRAM_cs(FRAM_cs), .LoRA_cs(LoRA_cs),
        
        // Handshake to SPI Master
        .spi_start(spi_start),
        .spi_done(spi_done),
        .spi_tx_byte(spi_tx_byte),
        .spi_rx_byte(spi_rx_byte),
        .master_cs(master_cs)
    );

    // --- Instantiate SPI Master (The Peripheral) ---
    spi_master_mode0 spi_inst (
        .clk(clk), .rst(rst),
        .start(spi_start),
        .data2send(spi_tx_byte),
        .miso(MISO),
        .done(spi_done),
        .sclk(spi_clk),
        .mosi(MOSI),
        .cs(master_cs), // Internal CS signal
        .data2receive(spi_rx_byte)
    );

endmodule