module FSM #(
    parameter ADC_WIDTH = 12,
    parameter SUNNY_THRESH = 12'h800,
    parameter VBAT_CRIT = 12'h400
)(
    input  logic rst, clk, wakeup,
    input  logic adc_EOC,
    input  logic [ADC_WIDTH-1:0] adc_data,
    output logic adc_conv_start,
    output logic [2:0] ana_ctrl,
    output logic en_sensor_vcc, en_radio_vcc,
    output logic FRAM_cs, LoRA_cs,
    output logic spi_start,
    input  logic spi_done,
    output logic [7:0] spi_tx_byte,
    input  logic [7:0] spi_rx_byte,
    input  logic master_cs
);

    typedef enum logic [3:0] {
        ST_RESET, ST_SHUTDOWN, ST_READ_TEMP, ST_READ_SOIL, ST_READ_CSOL, ST_READ_VSOL, 
        ST_DECIDE,  ST_READ_VBAT, ST_FRAM_WRITE, ST_LORA_FILL_BUF, ST_LORA_TRANSMIT
    } state_t;

    state_t curr_state, next_state;
    logic [ADC_WIDTH-1:0] temp_reg, soil_reg, vBat_reg, cSolar_reg;
    logic [7:0] data_buffer [0:15]; // Shrunk to 16 registers for area
    logic [15:0] fram_addr_ptr, read_ptr;
    logic [3:0] buf_ptr; // Corrected to 4 bits for 16-entry buffer
    logic [1:0] byte_step;

    always_ff @(posedge clk or posedge rst) begin
        if (rst) begin
            curr_state     <= ST_RESET;
            fram_addr_ptr  <= 16'd0;
            read_ptr       <= 16'd0;
            byte_step      <= 2'd0;
            buf_ptr        <= 4'd0; // Corrected bit-width
            temp_reg       <= 0;
            soil_reg       <= 0;
            vBat_reg       <= 0;
            cSolar_reg     <= 0;
        end else begin
            curr_state <= next_state;

            if (adc_EOC) begin
                case (curr_state)
                    ST_READ_TEMP: temp_reg   <= adc_data;
                    ST_READ_SOIL: soil_reg   <= adc_data;
                    ST_READ_CSOL: cSolar_reg <= adc_data;
                    ST_READ_VBAT: vBat_reg   <= adc_data;
                    default: ; 
                endcase
            end

            if (curr_state == ST_FRAM_WRITE && spi_done) begin
                if (byte_step == 2'd2) begin
                    byte_step <= 0;
                    fram_addr_ptr <= fram_addr_ptr + 16'd3;
                end else byte_step <= byte_step + 2'd1;
            end

            if (curr_state == ST_LORA_FILL_BUF && spi_done) begin
                data_buffer[buf_ptr] <= spi_rx_byte;
                buf_ptr  <= buf_ptr + 4'd1; // Corrected bit-width
                read_ptr <= read_ptr + 16'd1;
            end
            
            if (curr_state == ST_SHUTDOWN) buf_ptr <= 4'd0;
        end
    end

    always_comb begin
        next_state     = curr_state;
        adc_conv_start = 1'b0;
        ana_ctrl       = 3'b000;
        en_sensor_vcc  = 1'b0;
        en_radio_vcc   = 1'b0;
        FRAM_cs        = 1'b1;
        LoRA_cs        = 1'b1;
        spi_start      = 1'b0;
        spi_tx_byte    = 8'h00;

        case (curr_state)
            ST_RESET:    next_state = ST_SHUTDOWN;
            ST_SHUTDOWN: if (wakeup) next_state = ST_READ_TEMP;

            ST_READ_TEMP: begin
                en_sensor_vcc = 1'b1; ana_ctrl = 3'b000; adc_conv_start = 1'b1;
                if (adc_EOC) next_state = ST_READ_SOIL;
            end
            ST_READ_SOIL: begin
                en_sensor_vcc = 1'b1; ana_ctrl = 3'b001; adc_conv_start = 1'b1;
                if (adc_EOC) next_state = ST_READ_CSOL;
            end
            ST_READ_CSOL: begin
                en_sensor_vcc = 1'b1; ana_ctrl = 3'b010; adc_conv_start = 1'b1;
                if (adc_EOC) next_state = ST_READ_VSOL;
            end
            ST_READ_VSOL: begin
                en_sensor_vcc = 1'b1; ana_ctrl = 3'b011; adc_conv_start = 1'b1;
                if (adc_EOC) next_state = ST_READ_VBAT;
            end
            ST_READ_VBAT: begin
                en_sensor_vcc = 1'b1; ana_ctrl = 3'b100; adc_conv_start = 1'b1;
                if (adc_EOC) next_state = ST_DECIDE;
            end

            ST_DECIDE: begin
                en_sensor_vcc = 1'b1;
                if (vBat_reg < VBAT_CRIT) next_state = ST_SHUTDOWN;
                else if (cSolar_reg >= SUNNY_THRESH && fram_addr_ptr > 0) next_state = ST_LORA_FILL_BUF;
                else next_state = ST_FRAM_WRITE;
            end

            ST_FRAM_WRITE: begin
                en_radio_vcc = 1'b1; FRAM_cs = master_cs; spi_start = 1'b1;
                case(byte_step)
                    2'd0: spi_tx_byte = temp_reg[11:4];
                    2'd1: spi_tx_byte = {temp_reg[3:0], soil_reg[11:8]};
                    2'd2: spi_tx_byte = soil_reg[7:0];
                    default: spi_tx_byte = 8'h00;
                endcase
                if (spi_done && byte_step == 2'd2) next_state = ST_SHUTDOWN;
            end

            ST_LORA_FILL_BUF: begin
                en_radio_vcc = 1'b1; FRAM_cs = master_cs; spi_tx_byte = 8'hFF; spi_start = 1'b1;
                if (spi_done) begin
                    // Corrected check for 16-register buffer
                    if (buf_ptr == 4'd15 || read_ptr >= (fram_addr_ptr - 16'd1)) next_state = ST_LORA_TRANSMIT;
                end
            end

            ST_LORA_TRANSMIT: begin
                en_radio_vcc = 1'b1; LoRA_cs = master_cs; spi_tx_byte = data_buffer[buf_ptr]; spi_start = 1'b1;
                if (spi_done) begin
                    if (buf_ptr == 4'd15 || read_ptr >= fram_addr_ptr) next_state = ST_SHUTDOWN;
                    else next_state = ST_LORA_FILL_BUF;
                end
            end
            default: next_state = ST_SHUTDOWN;
        endcase
    end
endmodule
