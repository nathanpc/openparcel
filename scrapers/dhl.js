(function () {
	let data = OpenParcel.data.create();

	// Parses the addresses in any of the formats used by DHL.
	const parseAddress = function (line) {
		const address = OpenParcel.data.createAddress();
		const parts = line.split(" - ");

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
	};

	// Parses a tracking history item.
	const parseHistoryItem = function (item, date) {
		// Set the appropriate time.
		const timeStr = item.querySelector(".c-tracking-result--checkpoint-time").innerText;
		const match = timeStr.match(/(\d+):(\d+)/);
		if (match !== null)
			date.setUTCHours(Number(match[1]), Number(match[2]));

		// Create the update object.
		const details = item.querySelector(".c-tracking-result--checkpoint-right p.bold");
		const update = OpenParcel.data.createUpdate(details.innerText, null, {
			timestamp: date.toISOString()
		});

		// Get the update location.
		const locStr = item.querySelector(".c-tracking-result--checkpoint--more").innerText;
		if (locStr.length > 0)
			update.location = parseAddress(locStr);

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
		if (update.title.includes("Delivered") || update.title.includes("Delivery successful")) {
			update.status = OpenParcel.data.createStatus("delivered", update.title, {
				to: null
			});
		} else if (update.title.includes("Being delivered") || update.title.includes("with courier")) {
			update.status = OpenParcel.data.createStatus("delivering",
				update.title);
		} else if (update.title.includes("picked up") || update.title.includes("posted")) {
			update.status = OpenParcel.data.createStatus("posted",
				update.title);
		} else if (update.title.includes("electronically")) {
			update.status = OpenParcel.data.createStatus("created", update.title, {
				timestamp: null
			});
		} else if (update.title.includes("Clearance processing complete")) {
			update.status = OpenParcel.data.createStatus("customs-cleared`",
				update.title);
		} else if (update.title.includes("Delivery not possible")) {
			update.status = OpenParcel.data.createStatus("delivery-attempt",
				update.title);
		} else if (update.title.includes("on hold")) {
			update.status = OpenParcel.data.createStatus("issue",
				update.title);
		}

		return update;
	};

	// Get tracking code, origin, and destination addresses.
	data.trackingCode = document.querySelector(".c-tracking-result--code").innerText.split(":")[1].trim();
	const addressRegex = new RegExp("[^:]+[\s:]+(.+)", "");
	data.origin = parseAddress(addressRegex.exec(
		document.querySelector(".c-tracking-result--origin").innerText)[1].trim());
	data.destination = parseAddress(addressRegex.exec(
		document.querySelector(".c-tracking-result--destination").innerText)[1].trim());

	// Parse tracking history.
	document.querySelectorAll(".c-tracking-result--checkpoint-info").forEach(function (checkpoint) {
		let date = null;
		checkpoint.querySelectorAll("li").forEach(function (item, index) {
			// First item contains the date.
			if (index === 0) {
				const dateStr= item.querySelector(".c-tracking-result--checkpoint-date").innerText;
				const match = dateStr.match(/(\w+), (\d+) (\d+)/);

				date = new Date(
					Number(match[3]),  // Year
					OpenParcel.calendar.getMonth(match[1]),  // Month
					Number(match[2])   // Day
				);
			}

			// Build up the tracking history update object.
			data.history.push(parseHistoryItem(item, date));
		});
	});

	// Set the current delivery status.
	if (data.history.length > 0)
		data.status = data.history[0].status;

	return OpenParcel.data.finalTouches(data);
})();
