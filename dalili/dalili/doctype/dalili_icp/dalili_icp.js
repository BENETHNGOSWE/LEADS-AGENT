frappe.ui.form.on("Dalili ICP", {
	refresh(frm) {
		if (frm.is_new()) return;

		frm.add_custom_button(__("Preview matches"), () => {
			frappe.show_alert({ message: __("Sampling the universe…"), indicator: "blue" });
			frappe.call({
				method: "dalili.api.preview",
				args: { message: frm.doc.prompt_text || frm.doc.icp_name, limit: 5 },
				callback: (r) => {
					const data = r.message || {};
					const rows = (data.samples || [])
						.map(
							(s) =>
								`<tr><td><b>${frappe.utils.escape_html(s.company_name || "")}</b></td>
								 <td>${frappe.utils.escape_html(s.region || "")}</td>
								 <td>${frappe.utils.escape_html(s.phone || "")}</td></tr>`
						)
						.join("");
					frappe.msgprint({
						title: __("Sample of the universe"),
						message: rows
							? `<table class="table table-bordered"><thead><tr>
								<th>${__("Company")}</th><th>${__("Region")}</th><th>${__("Phone")}</th>
								</tr></thead><tbody>${rows}</tbody></table>
								<p class="text-muted small">${__("Estimated universe")}: ${data.universe_estimate || 0}</p>`
							: `<p>${__("No matches yet. Check the sector and region, or turn on Demo Mode.")}</p>`,
						wide: true,
					});
				},
			});
		});

		frm.add_custom_button(
			__("Run agent"),
			() => {
				frappe.confirm(
					__("Run the agent for {0}? This queues a background job.", [frm.doc.icp_name]),
					() => {
						frappe.call({
							method: "dalili.api.enqueue_run",
							args: { icp: frm.doc.name },
							freeze: true,
							freeze_message: __("Queuing…"),
							callback: (r) => {
								if (r.message) {
									frappe.show_alert({
										message: __("Run {0} queued. Open Dalili Agent Run to follow it.", [r.message]),
										indicator: "green",
									});
									frappe.set_route("Form", "Dalili Agent Run", r.message);
								}
							},
						});
					}
				);
			},
			__("Actions")
		);

		frm.add_custom_button(
			__("Run synchronously"),
			() => {
				frappe.call({
					method: "dalili.api.run_now",
					args: { icp: frm.doc.name },
					freeze: true,
					freeze_message: __("Running the pipeline…"),
					callback: (r) => {
						const run = r.message || {};
						frappe.show_alert({
							message: __("Delivered {0} leads", [(run.counters || {}).delivered || 0]),
							indicator: "green",
						});
						if (run.lead_list) {
							frappe.set_route("Form", "Dalili Lead List", run.lead_list);
						}
					},
				});
			},
			__("Actions")
		);

		if (frm.doc.last_run_on) {
			frm.dashboard.set_headline(
				__("Last run {0} · {1} leads delivered in total", [
					frappe.datetime.str_to_user(frm.doc.last_run_on),
					frm.doc.total_leads_delivered || 0,
				])
			);
		}
	},
});
