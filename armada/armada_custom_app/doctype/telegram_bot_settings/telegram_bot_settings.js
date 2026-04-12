frappe.ui.form.on("Telegram Bot Settings", {
    refresh(frm) {
        // Ko'z ikonkasi bilan show/hide toggle
        const $wrapper = frm.get_field("bot_token").$wrapper;
        const $input  = $wrapper.find("textarea");

        // Dastlab yashirin
        $input.css({
            "-webkit-text-security": "disc",
            "letter-spacing": "2px",
            "font-family": "monospace"
        });

        // Agar tugma allaqachon qo'shilgan bo'lsa — qayta qo'shmaslik
        if ($wrapper.find(".token-eye-btn").length) return;

        const $eyeBtn = $(`
            <button class="btn btn-xs btn-default token-eye-btn"
                    title="Ko'rish / Yashirish"
                    style="position:absolute; right:8px; top:6px;
                           background:none; border:none; cursor:pointer;
                           font-size:16px; color:#6c757d; z-index:10;">
                👁
            </button>
        `);

        $wrapper.find(".control-input-wrapper").css("position", "relative");
        $wrapper.find(".control-input-wrapper").append($eyeBtn);

        let visible = false;
        $eyeBtn.on("click", function (e) {
            e.preventDefault();
            visible = !visible;
            if (visible) {
                $input.css({
                    "-webkit-text-security": "none",
                    "letter-spacing": "normal"
                });
                $eyeBtn.text("🙈");
            } else {
                $input.css({
                    "-webkit-text-security": "disc",
                    "letter-spacing": "2px"
                });
                $eyeBtn.text("👁");
            }
        });
    }
});
