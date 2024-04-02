class Carrier extends OpenParcel {
	errorCheck() {
		// Check if the parcel tracking code is wrong.
		const tooltip = document.querySelector(
			".el-table .el-table_1_column_3 .el-tooltip.el-tag--info");
		if ((tooltip !== null) && tooltip.innerText.includes("Not Found"))
			return new ParcelError(ParcelError.Code.ParcelNotFound);

		// Check if an actual error happened with the backend of the service.
		const empty = document.querySelector(
			".el-table__empty-block .el-table__empty-text .empty");
		if ((empty !== null) && (empty.innerText.includes("No data")))
			return new ParcelError(ParcelError.Code.Unknown);

		return null;
	}

	scrape() {
		const base = this;

		// Check for errors, just in case.
		const error = this.errorCheck();
		if (error !== null)
			return error;

		// Get tracking code, origin, and destination addresses.
		this.parcel.trackingCode = document.querySelector(
			".el-table__body tr.el-table__row.expanded .el-tooltip.tooltip-item").innerText;
		const countries = document.querySelector(
			".el-table__body tr.el-table__row.expanded p span").innerText.split(" →");
		this.parcel.origin = new ParcelLocation(null, null, null, null,
			countries[0]);
		this.parcel.destination = new ParcelLocation(null, null, null, null,
			countries[1]);

		// Parse tracking code and tracking history.
		const timeline = document.querySelectorAll("#timeline")[1];
		timeline.querySelectorAll(".timeline-item").forEach((item) => {
			base.parseTimelineItem(item);
		});

		// TODO: Report on last mile tracking.

		return this.parcel;
	}

	/**
	 * Parses a timeline item and populates our tracking history array with its
	 * contents.
	 *
	 * @param item {Element} Timeline item element.
	 */
	parseTimelineItem(item) {
		// Get the base date for the timeline item.
		const dateElem = item.querySelectorAll(".left .left-item.xingqi > div")[1];
		const match = dateElem.innerText.match(/(\w+),(\d+),(\d+)/);
		const date = new ParcelTimestamp(new Date(
			Number(match[3]),  // Year
			ParcelTimestamp.getMonthIndex(match[1]),  // Month
			Number(match[2])   // Day
		));

		// Go through the actual history items in the timeline item.
		const leftItems = item.querySelectorAll(".left .left-item");
		const rightItems = item.querySelectorAll(".right .right-item");
		for (let i = 0; i < (rightItems.length - 1); i++) {
			// Parse the update item.
			this.parcel.appendUpdate(this.parseHistoryItem(leftItems[i + 1],
				rightItems[(i === 0) ? 0 : i + 1], date.clone()));
		}
	}

	/**
	 * Parses a tracking history item.
	 *
	 * @param {Element}         left      HTML element to the left of the item block.
	 * @param {Element}         right     HTML element to the right of the item block.
	 * @param {ParcelTimestamp} timestamp Timestamp when this update occurred.
	 *
	 * @returns {ParcelUpdate} OpenParcel tracking history item object.
	 */
	parseHistoryItem(left, right, timestamp) {
		// Get the right side elements separated and build up the update object.
		const rightElements = right.querySelectorAll("div");
		const update = new ParcelUpdate(rightElements[0].innerText);

		// Get our full timestamp.
		const match = left.querySelector("div").innerText
			.match(/(\d+):(\d+):(\d+)/);
		timestamp.setTime(Number(match[1]), Number(match[2]),
			Number(match[3]));
		update.timestamp = timestamp;

		// Build up the location.
		const locString = rightElements[1].innerText;
		if (locString.length > 0) {
			update.location = new ParcelLocation();
			const commaPos = locString.lastIndexOf(", ");

			if (locString.length === 2) {
				// We only have the country code.
				update.location.country = locString;
			} else if (commaPos !== 0) {
				// Looks like we have more information.
				update.location.addressLine = locString.substring(0, commaPos);
				update.location.country = locString.substring(commaPos + 2);
			} else {
				// Edge cases. Let's play safe.
				update.location.addressLine = locString;
			}
		}

		// Check if we have a special status to report.
		if (update.title.includes("Shipment information received")) {
			this.parcel.creationDate = update.timestamp;
			update.status = new ParcelStatus(ParcelStatus.Type.Created, update.title, {
				timestamp: this.parcel.creationDate.toString()
			});
		} else if (update.title.includes("flight has departed")) {
			update.status = new ParcelStatus(ParcelStatus.Type.DepartedOrigin, update.title, {
				location: update.location
			});
		} else if (update.title.includes("flight has arrived")) {
			update.status = new ParcelStatus(ParcelStatus.Type.ArrivedDestination, update.title, {
				location: update.location
			});
		}

		return update;
	}
}
