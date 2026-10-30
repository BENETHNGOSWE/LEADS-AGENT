frappe.ui.form.on("Dalili Lead List", {
	refresh(frm) {
		if (frm.is_new()) return;

		frm.add_custom_button(__("Copy WhatsApp brief"), () => {
			frappe.call({
				method: "dalili.api.get_brief",
				args: { lead_list: frm.doc.name, channel: "text" },
				callback: async (r) => {
					const text = (r.message || {}).content || "";
					try {
						await navigator.clipboard.writeText(text);
						frappe.show_alert({ message: __("Brief copied"), indicator: "green" });
					} catch (e) {
						frappe.msgprint({
							title: __("WhatsApp brief"),
							message: `<pre style="white-space:pre-wrap">${frappe.utils.escape_html(text)}</pre>`,
							wide: true,
						});
					}
				},
			});
		});

		frm.add_custom_button(__("Print brief"), () => {
			window.open(
				`/printview?doctype=Dalili%20Lead%20List&name=${encodeURIComponent(frm.doc.name)}&format=Dalili%20Lead%20Brief&no_letterhead=1`,
				"_blank"
			);
		});

		frm.add_custom_button(__("Download CSV"), () => {
			frappe.call({
				method: "dalili.api.export_csv",
				args: { lead_list: frm.doc.name },
				callback: (r) => {
					const url = (r.message || {}).file_url;
					if (url) window.open(url, "_blank");
				},
			});
		});

		frm.add_custom_button(
			__("Mark delivered"),
			() => {
				const dialog = new frappe.ui.Dialog({
					title: __("Mark as delivered"),
					fields: [
						{
							fieldname: "channel",
							label: __("Channel"),
							fieldtype: "Select",
							options: ["WhatsApp", "Email", "Print", "CRM"],
							default: "WhatsApp",
						},
						{ fieldname: "to", label: __("Delivered to"), fieldtype: "Data" },
					],
					primary_action_label: __("Confirm"),
					primary_action(values) {
						frappe.call({
							method: "dalili.api.mark_delivered",
							args: { lead_list: frm.doc.name, channel: values.channel, to: values.to },
							callback: () => {
								dialog.hide();
								frm.reload_doc();
							},
						});
					},
				});
				dialog.show();
			},
			__("Actions")
		);

		if (frm.doc.avg_score) {
			frm.dashboard.set_headline(
				__("{0} prospects · {1} verified · average score {2}", [
					frm.doc.total_prospects || 0,
					frm.doc.verified_count || 0,
					frm.doc.avg_score,
				])
			);
		}
	},
});
