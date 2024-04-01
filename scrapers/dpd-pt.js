class Carrier extends OpenParcel {
	errorCheck() {
		const item = document.querySelector("#content strong")
		if ((item !== null) && item.innerText.includes("No results were found"))
			return new ParcelError(ParcelError.Code.ParcelNotFound);

		return null;
	}

	scrape() {
		const base = this;

		// Check for errors, just in case.
		const error = this.errorCheck();
		if (error !== null)
			return error;

		// Parse tracking code and tracking history.
		const mainTable = document.querySelector("#content .table-responsive table");
		this.parcel.trackingCode = document.querySelector(
			"#content .panel.panel-default .panel-heading span").innerText.split(" ")[2];
		mainTable.querySelectorAll("tbody tr").forEach(function (item) {
			base.parcel.appendUpdate(base.parseHistoryItem(item));
		});

		return this.parcel;
	}

	/**
	 * Parses a tracking history item.
	 *
	 * @param {Element} item HTML element of the update item block.
	 *
	 * @returns {ParcelUpdate} OpenParcel tracking history item object.
	 */
	parseHistoryItem(item) {
		const cols = item.getElementsByTagName("td");

		// Build up the tracking history update object.
		const update = new ParcelUpdate(cols[2].innerText);
		if (cols[3].innerText.length > 0)
			update.description = cols[3].innerText;

		// Parse the timestamp.
		const match = cols[1].innerText.match(/(\d+)\/(\d+)\/(\d+) (\d+):(\d+)/);
		update.setTimestamp(new Date(
			Number(match[1]),      // Year
			Number(match[2]) - 1,  // Month
			Number(match[3]),      // Day
			Number(match[4]),      // Hours
			Number(match[5])       // Minutes
		));

		// Check if we have a location to report.
		if (cols[4].querySelector("a") !== null) {
			const mapsLink = cols[4].querySelector("a").href;
			const match = mapsLink.match(/place\?q=([^%]+)%2C([^&]+)/);

			if (match !== null) {
				update.location = new ParcelLocation().setCoords(
					Number(match[1]), Number(match[2]));
			}
		}

		// Check if we have a special status to report.
		const code = cols[0].innerText;
		if (code === "POD") {
			update.status = new ParcelStatus(ParcelStatus.Type.Delivered, update.description, {
				to: update.description
			});
		} else if (update.title.includes("RECEIVED BY PUDO")) {
			update.status = new ParcelStatus(ParcelStatus.Type.WaitingPickup, update.title, {
				location: null,
				until: null
			});
		} else if (code === "OFD") {
			update.status = new ParcelStatus(ParcelStatus.Type.Delivering,
				update.title);
		} else if (code === "413") {
			update.status = new ParcelStatus(ParcelStatus.Type.Issue, update.title);
		}

		return update;
	}
}
