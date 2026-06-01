// Copyright (c) 2025, Sardorbek and contributors
// For license information, please see license.txt

frappe.ui.form.on('Production Entry', {
    setup: function(frm) {
        // Set default target warehouse for new documents
        if (frm.is_new() && !frm.doc.target_warehouse) {
            frm.set_value("target_warehouse", "Склад Производство - AM");
        }
    },

    refresh: function(frm) {
        // Set query for BOM - only show BOMs for selected item
        frm.set_query("bom_no", function() {
            return {
                filters: {
                    "item": frm.doc.item_to_manufacture,
                    "is_active": 1,
                    "docstatus": 1
                }
            };
        });

        // Set query for target warehouse
        frm.set_query("target_warehouse", function() {
            return {
                filters: {
                    "is_group": 0,
                    "company": frm.doc.company
                }
            };
        });

        // Add button to refresh available qty
        if (frm.doc.docstatus === 0) {
            frm.add_custom_button(__('Refresh Available Qty'), function() {
                update_all_available_qty(frm);
            });
        }

        if (frm.doc.docstatus === 1) {
            frm.add_custom_button(__('Print Barcode'), function() {
                print_production_barcodes(frm, false);
            });
        }
    },

    on_submit: function(frm) {
        print_production_barcodes(frm, true);
    },

    item_to_manufacture: function(frm) {
        if (frm.doc.item_to_manufacture) {
            // Get default BOM for item
            frappe.call({
                method: "armada.armada_custom_app.doctype.production_entry.production_entry.get_bom_for_item",
                args: {
                    item_code: frm.doc.item_to_manufacture
                },
                callback: function(r) {
                    if (r.message) {
                        frm.set_value("bom_no", r.message);
                    } else {
                        frm.set_value("bom_no", "");
                        frappe.msgprint(__("No active BOM found for {0}", [frm.doc.item_to_manufacture]));
                    }
                }
            });
        } else {
            frm.set_value("bom_no", "");
            frm.clear_table("items");
            frm.refresh_field("items");
        }
    },

    bom_no: function(frm) {
        if (frm.doc.bom_no && frm.doc.qty_to_manufacture) {
            fetch_bom_items(frm);
        }
    },

    qty_to_manufacture: function(frm) {
        if (frm.doc.bom_no && frm.doc.qty_to_manufacture > 0) {
            fetch_bom_items(frm);
        }
    },

    posting_date: function(frm) {
        update_all_available_qty(frm);
    },

    posting_time: function(frm) {
        update_all_available_qty(frm);
    },

    target_warehouse: function(frm) {
        // Update all source_warehouse in items when target_warehouse changes
        if (frm.doc.target_warehouse && frm.doc.items && frm.doc.items.length > 0) {
            frm.doc.items.forEach(function(row) {
                frappe.model.set_value(row.doctype, row.name, "source_warehouse", frm.doc.target_warehouse);
            });
            frm.refresh_field("items");
            update_all_available_qty(frm);
        }
    }
});

frappe.ui.form.on('Production Entry Item', {
    item_code: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.item_code && row.source_warehouse) {
            update_available_qty(frm, row);
        }
    },

    source_warehouse: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.item_code && row.source_warehouse) {
            update_available_qty(frm, row);
        }
    },

    required_qty: function(frm, cdt, cdn) {
        // Allow manual editing, just refresh
        frm.refresh_field("items");
    }
});

function fetch_bom_items(frm) {
    frappe.call({
        method: "armada.armada_custom_app.doctype.production_entry.production_entry.get_bom_items",
        args: {
            bom_no: frm.doc.bom_no,
            qty_to_manufacture: frm.doc.qty_to_manufacture,
            posting_date: frm.doc.posting_date,
            posting_time: frm.doc.posting_time,
            source_warehouse: frm.doc.target_warehouse || ""
        },
        callback: function(r) {
            if (r.message) {
                frm.clear_table("items");
                r.message.forEach(function(item) {
                    let row = frm.add_child("items");
                    row.item_code = item.item_code;
                    row.item_name = item.item_name;
                    row.source_warehouse = item.source_warehouse;
                    row.required_qty = item.required_qty;
                    row.available_qty = item.available_qty;
                    row.uom = item.uom;
                });
                frm.refresh_field("items");
            }
        }
    });
}

function update_all_available_qty(frm) {
    if (!frm.doc.items || frm.doc.items.length === 0) return;

    frm.doc.items.forEach(function(item) {
        if (item.item_code && item.source_warehouse) {
            update_available_qty(frm, item);
        }
    });
}

function update_available_qty(frm, row) {
    frappe.call({
        method: "armada.armada_custom_app.doctype.production_entry.production_entry.get_available_qty_for_item",
        args: {
            item_code: row.item_code,
            warehouse: row.source_warehouse,
            posting_date: frm.doc.posting_date,
            posting_time: frm.doc.posting_time
        },
        callback: function(r) {
            if (r.message !== undefined) {
                frappe.model.set_value(row.doctype, row.name, "available_qty", r.message);
            }
        }
    });
}

const QZ_TRAY_URL = "https://cdn.jsdelivr.net/npm/qz-tray@2.2.4/qz-tray.js";
const QZ_PRINTER_STORAGE_KEY = "armada_production_barcode_printer";
const PRINTED_DOC_STORAGE_PREFIX = "armada_production_barcode_printed:";

function print_production_barcodes(frm, automatic) {
    if (!frm.doc.name || frm.doc.docstatus !== 1) return;

    const printed_key = PRINTED_DOC_STORAGE_PREFIX + frm.doc.name;
    if (automatic && localStorage.getItem(printed_key)) return;

    frappe.call({
        method: "armada.armada_custom_app.doctype.production_entry.production_entry.get_production_barcode_payload",
        args: { production_entry: frm.doc.name },
        freeze: !automatic,
        freeze_message: __("Preparing barcode labels..."),
        callback: function(r) {
            if (!r.message) return;

            print_zpl_with_qz(r.message)
                .then(function() {
                    localStorage.setItem(printed_key, "1");
                    frappe.show_alert({ message: __("Barcode labels sent to printer"), indicator: "green" });
                })
                .catch(function(error) {
                    frappe.msgprint({ title: __("Barcode Print Failed"), indicator: "red", message: get_qz_error_message(error) });
                });
        }
    });
}

function print_zpl_with_qz(label) {
    return load_qz_tray()
        .then(connect_qz_tray)
        .then(get_qz_printer)
        .then(function(printer_name) {
            const config = qz.configs.create(printer_name, {
                forceRaw: true,
                jobName: __("Production Barcode {0}", [label.production_entry])
            });
            return qz.print(config, [{ type: "raw", format: "command", data: build_production_barcode_zpl(label) }]);
        });
}

function load_qz_tray() {
    if (window.qz) return Promise.resolve();

    return new Promise(function(resolve, reject) {
        const existing_script = document.querySelector('script[data-armada-qz-tray="1"]');
        if (existing_script) {
            existing_script.addEventListener("load", resolve, { once: true });
            existing_script.addEventListener("error", reject, { once: true });
            return;
        }
        const script = document.createElement("script");
        script.src = QZ_TRAY_URL;
        script.async = true;
        script.dataset.armadaQzTray = "1";
        script.onload = resolve;
        script.onerror = function() { reject(__("Could not load QZ Tray JavaScript library")); };
        document.head.appendChild(script);
    });
}

function connect_qz_tray() {
    if (!window.qz) return Promise.reject(__("QZ Tray JavaScript library is not available"));
    if (qz.websocket.isActive()) return Promise.resolve();
    return qz.websocket.connect();
}

function get_qz_printer() {
    const saved_printer = localStorage.getItem(QZ_PRINTER_STORAGE_KEY);
    if (saved_printer) return Promise.resolve(saved_printer);

    return get_qz_printer_options().then(function(printers) {
        return new Promise(function(resolve, reject) {
            if (!printers.length) { reject(__("No printers found in QZ Tray")); return; }

            let selected = false;
            const dialog = new frappe.ui.Dialog({
                title: __("Select Barcode Printer"),
                fields: [{ fieldtype: "Select", fieldname: "printer", label: __("Printer"), options: printers.join("\n"), reqd: 1 }],
                primary_action_label: __("Save and Print"),
                primary_action: function(values) {
                    selected = true;
                    localStorage.setItem(QZ_PRINTER_STORAGE_KEY, values.printer);
                    dialog.hide();
                    resolve(values.printer);
                }
            });
            dialog.$wrapper.on("hidden.bs.modal", function() { if (!selected) reject(__("Barcode printer was not selected")); });
            dialog.show();
        });
    });
}

function get_qz_printer_options() {
    if (qz.printers.details) {
        return qz.printers.details().then(function(details) {
            return details.map(function(p) { return p.name || p; }).filter(Boolean);
        });
    }
    return qz.printers.find().then(function(printer) { return printer ? [printer] : []; });
}

function build_production_barcode_zpl(label) {
    const PW = 812;
    const LL = 1218;
    const Y_START = 70;
    const HORIZONTAL_SHIFT = -35;
    const FULL_WIDTH = 1080;
    const LEFT_COL_Y = 70;
    const RIGHT_COL_Y = 625;
    const COL_WIDTH = 515;

    const item_code_text = fit_label_text(label_value(label.item_code), 28);
    const barcode_value = zpl_barcode(label.barcode);
    const datetime = zpl_text(format_label_datetime(label));

    const fp_type_text = "FP Type: " + fit_label_text(label_value(label.fp_type), 24);
    const segment_text = "Segment: " + fit_label_text(label_value(label.segment), 24);
    const product_type_text = "Product Type: " + fit_label_text(label_value(label.product_type), 22);
    const standard_text = "Standard: " + fit_label_text(label_value(label.standard), 24);

    const item_font = get_item_code_font(item_code_text);
    const fp_segment_font = get_pair_font(fp_type_text, segment_text);
    const product_standard_font = get_pair_font(product_type_text, standard_text);

    const barcode_module = barcode_value.length > 18 ? 3 : 4;
    const barcode_height = 300;
    const estimated_barcode_width = (barcode_value.length * 11 + 35) * barcode_module;
    let barcode_y = Y_START + Math.floor((FULL_WIDTH - estimated_barcode_width) / 2);
    barcode_y = Math.max(Y_START + 10, barcode_y);
    barcode_y = Math.min(Y_START + FULL_WIDTH - estimated_barcode_width - 10, barcode_y);

    const start_y = shift_label_y(Y_START, HORIZONTAL_SHIFT);
    const left_col_y = shift_label_y(LEFT_COL_Y, HORIZONTAL_SHIFT);
    const right_col_y = shift_label_y(RIGHT_COL_Y, HORIZONTAL_SHIFT);
    const shifted_barcode_y = shift_label_y(barcode_y, HORIZONTAL_SHIFT);

    const item_code_graphic = render_text_graphic(item_code_text, { width: FULL_WIDTH, height: 150, font_size: item_font.height, max_width: FULL_WIDTH - 180, min_font_size: 56, weight: 800 });
    const barcode_text_graphic = render_text_graphic(barcode_value, { width: FULL_WIDTH, height: 80, font_size: 66, weight: 800 });
    const date_graphic = render_text_graphic("Date: " + datetime, { width: FULL_WIDTH, height: 68, font_size: 54, weight: 800 });
    const fp_type_graphic = render_text_graphic(fp_type_text, { width: COL_WIDTH, height: 68, font_size: fp_segment_font.height, weight: 800 });
    const segment_graphic = render_text_graphic(segment_text, { width: COL_WIDTH, height: 68, font_size: fp_segment_font.height, weight: 800 });
    const product_type_graphic = render_text_graphic(product_type_text, { width: COL_WIDTH, height: 64, font_size: product_standard_font.height, weight: 800 });
    const standard_graphic = render_text_graphic(standard_text, { width: COL_WIDTH, height: 64, font_size: product_standard_font.height, weight: 800 });

    return [
        "^XA", "^CI28", "^PW" + PW, "^LL" + LL, "^LH0,0",
        zpl_graphic(650, start_y, item_code_graphic),
        "^FO330," + shifted_barcode_y + "^BY" + barcode_module + ",2," + barcode_height + "^BCR," + barcode_height + ",N,N,N^FD" + barcode_value + "^FS",
        zpl_graphic(250, start_y, barcode_text_graphic),
        zpl_graphic(185, start_y, date_graphic),
        zpl_graphic(110, left_col_y, fp_type_graphic),
        zpl_graphic(110, right_col_y, segment_graphic),
        zpl_graphic(35, left_col_y, product_type_graphic),
        zpl_graphic(35, right_col_y, standard_graphic),
        "^PQ" + cint(label.qty) + ",0,1,Y",
        "^XZ"
    ].join("\n");
}

function shift_label_y(value, shift) { return Math.max(0, value + shift); }

function render_text_graphic(text, options) {
    const logical_width = Math.max(1, cint(options.width));
    const logical_height = Math.max(1, cint(options.height));
    let font_size = Math.max(1, cint(options.font_size));
    const min_font_size = Math.max(1, cint(options.min_font_size || font_size));
    const max_width = Math.max(1, cint(options.max_width || logical_width - 20));
    const font_weight = options.weight || 800;

    const logical_canvas = document.createElement("canvas");
    logical_canvas.width = logical_width;
    logical_canvas.height = logical_height;
    const logical_context = logical_canvas.getContext("2d");
    logical_context.clearRect(0, 0, logical_width, logical_height);
    logical_context.fillStyle = "#000";
    logical_context.textAlign = "center";
    logical_context.textBaseline = "middle";

    do {
        logical_context.font = font_weight + " " + font_size + "px Arial, 'DejaVu Sans', sans-serif";
        if (logical_context.measureText(String(text || "")).width <= max_width) break;
        font_size -= 2;
    } while (font_size > min_font_size);

    logical_context.fillText(String(text || ""), logical_width / 2, logical_height / 2);

    const rotated_canvas = document.createElement("canvas");
    rotated_canvas.width = logical_height;
    rotated_canvas.height = logical_width;
    const rotated_context = rotated_canvas.getContext("2d");
    rotated_context.clearRect(0, 0, rotated_canvas.width, rotated_canvas.height);
    rotated_context.translate(rotated_canvas.width, 0);
    rotated_context.rotate(Math.PI / 2);
    rotated_context.drawImage(logical_canvas, 0, 0);

    return canvas_to_zpl_gfa(rotated_canvas);
}

function canvas_to_zpl_gfa(canvas) {
    const context = canvas.getContext("2d");
    const image_data = context.getImageData(0, 0, canvas.width, canvas.height).data;
    const bytes_per_row = Math.ceil(canvas.width / 8);
    const total_bytes = bytes_per_row * canvas.height;
    let hex = "";

    for (let y = 0; y < canvas.height; y++) {
        for (let byte_index = 0; byte_index < bytes_per_row; byte_index++) {
            let byte = 0;
            for (let bit = 0; bit < 8; bit++) {
                const x = byte_index * 8 + bit;
                if (x >= canvas.width) continue;
                const offset = (y * canvas.width + x) * 4;
                const luminance = image_data[offset] * 0.299 + image_data[offset + 1] * 0.587 + image_data[offset + 2] * 0.114;
                if (image_data[offset + 3] > 64 && luminance < 220) byte |= 0x80 >> bit;
            }
            hex += byte.toString(16).padStart(2, "0").toUpperCase();
        }
    }

    return { data: "^GFA," + total_bytes + "," + total_bytes + "," + bytes_per_row + "," + hex, width: canvas.width, height: canvas.height };
}

function zpl_graphic(x, y, graphic) { return "^FO" + x + "," + y + graphic.data + "^FS"; }

function get_item_code_font(value) {
    const length = String(value || "").length;
    if (length <= 16) return { height: 98, width: 88 };
    if (length <= 22) return { height: 96, width: 68 };
    if (length <= 28) return { height: 80, width: 52 };
    return { height: 68, width: 40 };
}

function get_pair_font(left, right) {
    const length = Math.max(String(left || "").length, String(right || "").length);
    if (length <= 20) return { height: 48, width: 38 };
    if (length <= 28) return { height: 40, width: 30 };
    return { height: 34, width: 24 };
}

function fit_label_text(value, max_length) {
    const text = zpl_text(label_value(value));
    if (text.length <= max_length) return text;
    return text.slice(0, Math.max(0, max_length - 3)) + "...";
}

function label_value(value) {
    if (value === null || value === undefined || value === "") return "None";
    return String(value);
}

function format_label_datetime(label) {
    const date = label_value(label.posting_date);
    const time = label_value(label.posting_time);
    if (date === "None" && time === "None") return "None";
    if (time === "None") return date;
    if (date === "None") return time;
    return date + " " + time;
}

function zpl_text(value) { return String(value || "").replace(/[\^~\\]/g, " ").slice(0, 80); }
function zpl_barcode(value) { return String(value || "").replace(/[^A-Za-z0-9._-]/g, "").slice(0, 80); }
function cint(value) { return parseInt(value || 0, 10); }
function get_qz_error_message(error) {
    if (!error) return __("Unknown print error");
    if (error.message) return frappe.utils.escape_html(error.message);
    return frappe.utils.escape_html(String(error));
}
