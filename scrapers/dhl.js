class Carrier extends OpenParcel {
	errorCheck() {
		const errBlock = document.querySelector(
			".c-tracking-result--status-shipment-undefined");

		// Check for the existence of the error block element.
		if (errBlock !== null) {
			const errMessage = document.querySelector(
				".c-tracking-result--info .c-tracking-result-message--content"
			).innerText;

			// Parse the message contained within.
			if (errMessage.includes("tracking attempt was not successful")) {
				return new ParcelError(ParcelError.Code.ParcelNotFound);
			} else if (errMessage.includes("tracking code is invalid")) {
				return new ParcelError(ParcelError.Code.InvalidTrackingCode);
			}

			// Looks like it's a new message that we've never seen before.
			return new ParcelError(ParcelError.Code.Unknown);
		}

		return null;
	}

	scrape() {
		const base = this;

		// Check for errors.
		const error = this.errorCheck();
		if (error !== null)
			return error;

		// Get tracking code, origin, and destination addresses.
		this.parcel.trackingCode = document.querySelector(".c-tracking-result--code")
			.innerText.split(":")[1].trim();
		const addressRegex = new RegExp("[^:]+[\s:]+(.+)", "");
		this.parcel.origin = this.parseAddress(addressRegex.exec(
			document.querySelector(".c-tracking-result--origin").innerText)[1].trim());
		this.parcel.destination = this.parseAddress(addressRegex.exec(
			document.querySelector(".c-tracking-result--destination").innerText)[1].trim());

		// Parse tracking history.
		document.querySelectorAll(".c-tracking-result--checkpoint-info").forEach((checkpoint) => {
			let date = null;
			checkpoint.querySelectorAll("li").forEach((item, index) => {
				// First item contains the date.
				if (index === 0) {
					const dateStr = item.querySelector(
						".c-tracking-result--checkpoint-date").innerText;
					const match = dateStr.match(/(\w+), (\d+) (\d+)/);

					date = new ParcelTimestamp(new Date(
						Number(match[3]),  // Year
						ParcelTimestamp.getMonthIndex(match[1]),  // Month
						Number(match[2])   // Day
					));
				}

				// Build up the tracking history update object.
				base.parcel.appendUpdate(base.parseHistoryItem(item, date.clone()));
			});
		});

		return this.parcel;
	}

	/**
	 * Parses the addresses in any of the formats used by DHL.
	 *
	 * @param {string} line Address line from an element.
	 *
	 * @return {ParcelLocation} OpenParcel address object.
	 */
	parseAddress(line) {
		const address = new ParcelLocation();
		const parts = line.replace(/[\r\n\t]+/g, " ").split(" - ");

		// Non-detailed address.
		if (parts.length === 1) {
			address.country = parts[0].trim();
			return address;
		}

		// Detailed address.
		address.country = parts[parts.length - 1].trim();
		address.state = parts[parts.length - 2].trim();
		if (parts.length >= 3) {
			address.city = parts[parts.length - 3].trim().replace(
				"Service Area: ", "");
		}

		return address;
	}

	/**
	 * Parses a tracking history item.
	 *
	 * @param {Element} 		item HTML element of the update item block.
	 * @param {ParcelTimestamp} date Timestamp when this update occurred.
	 *
	 * @returns {ParcelUpdate} OpenParcel tracking history item object.
	 */
	parseHistoryItem(item, date) {
		// Set the appropriate time.
		const timeStr = item.querySelector(
			".c-tracking-result--checkpoint-time").innerText;
		const match = timeStr.match(/(\d+):(\d+)/);
		if (match !== null)
			date.setTime(Number(match[1]), Number(match[2]));

		// Create the update object.
		const details = item.querySelector(
			".c-tracking-result--checkpoint-right p.bold");
		const update = new ParcelUpdate(details.innerText, null, null, date);

		// Get the update location.
		const locStr = item.querySelector(".c-tracking-result--checkpoint--more").innerText;
		if (locStr.length > 0)
			update.location = this.parseAddress(locStr);

		// Check if we have anything for the description.
		const noteMatch = update.title.match(/(.+)\s+Note[\s:-]+(.+)/);
		if (noteMatch !== null) {
			update.title = noteMatch[1].trim();
			update.description = noteMatch[2].trim();
		}

		// Trim out any weird characters from title.
		if (update.title.endsWith("."))
			update.title = update.title.slice(0, -1)

		// Check if it was delivered.
		if (update.title.containsAny(["Delivered", "Delivery successful"])) {
			update.status = new ParcelStatus(ParcelStatus.Type.Delivered, update.title, {
				to: null
			});
		} else if (update.title.containsAny(["Being delivered", "with courier"])) {
			update.status = new ParcelStatus(ParcelStatus.Type.Delivering, update.title);
		} else if (update.title.containsAny(["picked up", "posted"])) {
			update.status = new ParcelStatus(ParcelStatus.Type.Posted, update.title);
		} else if (update.title.includes("electronically")) {
			update.status = new ParcelStatus(ParcelStatus.Type.Created, update.title, {
				timestamp: null
			});
		} else if (update.title.includes("Clearance processing complete")) {
			update.status = new ParcelStatus(ParcelStatus.Type.CustomsCleared, update.title);
		} else if (update.title.includes("Delivery not possible")) {
			update.status = new ParcelStatus(ParcelStatus.Type.DeliveryAttempt, update.title);
		} else if (update.title.includes("on hold")) {
			update.status = new ParcelStatus(ParcelStatus.Type.Issue, update.title);
		}

		return update;
	}
}