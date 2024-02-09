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

		/*
		// Check if it was delivered.
		if (update.title === "Entregue") {
			const recString = content.querySelector("[id*='FormatName'] [data-expression]").innerText.trim();
			update.status = OpenParcel.data.createStatus("delivered", recString, {
				to: recString.replace(/^Entregue\s+a:\s+/, "").trim()
			});
		} else if (update.title === "Em entrega") {
			update.status = OpenParcel.data.createStatus("delivering",
				update.description);
		} else if ((update.title === "No ponto de entrega") &&
				update.description.includes("disponível para levantamento")) {
			const locString = content.querySelector("[id*='Location'] [data-expression]").innerText.trim();
			update.status = OpenParcel.data.createStatus("pickup", locString, {
				location: locString.split(" até ")[0],
				until: null
			});

			// Calculate the until date.
			let until = timestamp;
			until.setUTCMonth(
				OpenParcel.calendar.getMonthPT(locString.split(" até ")[1].split(" ")[1]),
				Number(locString.split(" até ")[1].split(" ")[0]));
			if (until.getUTCMonth() < timestamp.getUTCMonth())
				until.setUTCFullYear(until.getUTCFullYear() + 1);
			update.status.data.until = until.toISOString();
		} else if (update.title === "Aceite") {
			update.status = OpenParcel.data.createStatus("posted",
				update.description);
		} else if (update.title === "Aguarda entrada nos CTT") {
			update.status = OpenParcel.data.createStatus("created", update.description, {
				timestamp: creationDate.toISOString()
			});
		}
		*/

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

    return data;
})();
