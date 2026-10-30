frappe.ui.form.on("Dalili Prospect", {
	refresh(frm) {
		if (frm.is_new()) return;

		// --- verification: the core daily action -------------------------
		frm.add_custom_button(
			__("Log verification"),
			() => {
				const contacts = (frm.doc.contacts || []).map((c) => c.name);
				frappe.call({
					method: "frappe.client.get_list",
					args: {
						doctype: "Dalili Contact",
						filters: { prospect: frm.doc.name },
						fields: ["name", "full_name", "role_title", "phone"],
						limit_page_length: 0,
					},
					callback: (r) => {
						const rows = r.message || [];
						const options = rows.length
							? rows.map((x) => `${x.name} · ${x.full_name} ${x.role_title ? "— " + x.role_title : ""}`)
							: [""];
						const dialog = new frappe.ui.Dialog({
							title: __("Log verification — {0}", [frm.doc.company_name]),
							fields: [
								{
									fieldname: "contact",
									label: __("Contact"),
									fieldtype: "Select",
									options: [""].concat(options),
									description: __("Leave blank to verify the company line"),
								},
								{
									fieldname: "method",
									label: __("Method"),
									fieldtype: "Select",
									options: [
										"Outbound call", "SMS ping", "WhatsApp check",
										"Website check", "Switchboard", "Email check", "Manual",
									],
									default: "Outbound call",
									reqd: 1,
								},
								{
									fieldname: "outcome",
									label: __("Outcome"),
									fieldtype: "Select",
									options: [
										"Answered - verified", "Wrong person", "Left company",
										"Disconnected", "No answer", "Do not call", "Wrong number",
									],
									default: "Answered - verified",
									reqd: 1,
								},
								{ fieldname: "notes", label: __("Notes"), fieldtype: "Small Text" },
							],
							primary_action_label: __("Save"),
							primary_action(values) {
								const contact = (values.contact || "").split(" · ")[0];
								frappe.call({
									method: "dalili.api.log_verification",
									args: {
										prospect: frm.doc.name,
										contact: contact || null,
										method: values.method,
										outcome: values.outcome,
										notes: values.notes,
									},
									freeze: true,
									callback: () => {
										dialog.hide();
										frm.reload_doc();
										frappe.show_alert({
											message: __("Verification recorded"),
											indicator: "green",
										});
									},
								});
							},
						});
						dialog.show();
					},
				});
			},
			__("Actions")
		);

		// --- conversion to ERPNext --------------------------------------
		if (!frm.doc.erpnext_lead) {
			frm.add_custom_button(__("Convert to ERPNext Lead"), () => {
				frappe.call({
					method: "dalili.api.convert",
					args: { prospect: frm.doc.name, contact: frm.doc.best_contact || null },
					freeze: true,
					callback: (r) => {
						const lead = (r.message || {}).lead;
						if (lead) {
							frappe.show_alert({ message: __("Lead {0} created", [lead]), indicator: "green" });
							frappe.set_route("Form", "Lead", lead);
						}
					},
				});
			});
		} else {
			frm.add_custom_button(__("Open Lead"), () => {
				frappe.set_route("Form", frm.doc.lead_doctype || "Lead", frm.doc.erpnext_lead);
			});
		}

		// --- WhatsApp deep link ------------------------------------------
		if (frm.doc.primary_whatsapp || frm.doc.primary_phone) {
			const number = (frm.doc.primary_whatsapp || frm.doc.primary_phone).replace(/\D/g, "");
			frm.add_custom_button(__("WhatsApp"), () => {
				window.open(`https://wa.me/${number}`, "_blank");
			});
		}

		// --- score explainability ----------------------------------------
		if (frm.doc.score_breakdown) {
			try {
				const breakdown = JSON.parse(frm.doc.score_breakdown);
				const reasons = breakdown.reasons || {};
				const html = Object.entries(breakdown.components || {})
					.map(([key, value]) => {
						const why = (reasons[key] || []).slice(0, 4).join(" · ");
						const weight = (breakdown.weights || {})[key] || 0;
						return `<tr>
							<td><b>${frappe.utils.escape_html(key)}</b></td>
							<td>${Math.round(value)}</td>
							<td class="text-muted">${weight}%</td>
							<td class="small text-muted">${frappe.utils.escape_html(why)}</td>
						</tr>`;
					})
					.join("");
				frm.dashboard.add_section(
					`<table class="table table-sm" style="margin:0">
						<thead><tr><th>${__("Component")}</th><th>${__("Score")}</th>
						<th>${__("Weight")}</th><th>${__("Why")}</th></tr></thead>
						<tbody>${html}</tbody></table>`,
					__("Score breakdown")
				);
			} catch (e) {
				/* malformed JSON should never break the form */
			}
		}
	},
});
