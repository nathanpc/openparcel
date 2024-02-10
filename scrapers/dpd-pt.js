(function () {
	let data = OpenParcel.data.create();
	const mainTable = document.querySelector("#content .table-responsive table");

	// Parse tracking code and tracking history.
	data.trackingCode = document.querySelector(
		"#content .panel.panel-default .panel-heading span").innerText.split(" ")[2];
	mainTable.querySelectorAll("tbody tr").forEach(function (item) {
		const cols = item.getElementsByTagName("td");

		// Build up the tracking history update object.
		const update = OpenParcel.data.createUpdate(cols[2].innerText, null);
		if (cols[3].innerText.length > 0)
			update.description = cols[3].innerText;

		// Parse the timestamp.
		const match = cols[1].innerText.match(/(\d+)\/(\d+)\/(\d+) (\d+):(\d+)/);
		update.timestamp = new Date(
			Number(match[1]),      // Year
			Number(match[2]) - 1,  // Month
			Number(match[3]),      // Day
			Number(match[4]),      // Hours
			Number(match[5])       // Minutes
		).toISOString();

		// Check if we have a location to report.
		if (cols[4].querySelector("a") !== null) {
			const mapsLink = cols[4].querySelector("a").href;
			const match = mapsLink.match(/place\?q=([^%]+)%2C([^&]+)/);

			if (match !== null) {
				update.location = OpenParcel.data.createAddress();
				update.location.coords.lat = Number(match[1]);
				update.location.coords.lng = Number(match[2]);
			}
		}

		// Check if we have a special status to report.
		const code = cols[0].innerText;
		if (code === "POD") {
			update.status = OpenParcel.data.createStatus("delivered", update.description, {
				to: update.description
			});
		} else if (update.title.includes("RECEIVED BY PUDO")) {
			update.status = OpenParcel.data.createStatus("pickup", update.title, {
				location: null,
				until: null
			});
		} else if (code === "OFD") {
			update.status = OpenParcel.data.createStatus("delivering",
				update.title);
		}

		// Append the update object to the tracking history array.
		data.history.push(update);
	});

	// Set the current delivery status.
	if (data.history.length > 0)
		data.status = data.history[0].status;

	return OpenParcel.data.finalTouches(data);
})();
