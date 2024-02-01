(function () {
	let data = {
		trackingCode: null,
		trackingUrl: window.location.href,
		creationDate: null,
		status: null,
		destination: null,
		history: []
	};

	// Converts a portuguese month name to month number.
	const getMonthPT = function (monthName) {
		switch (monthName) {
			case 'Jan':
			case 'Janeiro':
				return 0;
			case 'Fev':
			case 'Fevereiro':
				return 1;
			case 'Mar':
			case 'Março':
				return 2;
			case 'Abr':
			case 'Abril':
				return 3;
			case 'Mai':
			case 'Maio':
				return 4;
			case 'Jun':
			case 'Junho':
				return 5;
			case 'Jul':
			case 'Julho':
				return 6;
			case 'Ago':
			case 'Agosto':
				return 7;
			case 'Set':
			case 'Setembro':
				return 8;
			case 'Out':
			case 'Outubro':
				return 9;
			case 'Nov':
			case 'Novembro':
				return 10;
			case 'Dez':
			case 'Dezembro':
				return 11;
		}
	};

	// Parses a tracking history item.
	const parseHistoryItem = function (item, creationDate) {
		const content = item.querySelector("[id*=TimelineContent] [id*=Content]");
		const dtHtml = item.querySelectorAll("[id*=Left] [data-expression]");

		let update = {
			title: item.querySelector("[id*=TimelineContent] [id*=Title] [data-expression]").innerText.trim(),
			description: content.querySelector("[id*='Event'] [data-expression]").innerText.trim(),
			location: content.querySelector("[id*='Location'] [data-expression]").innerText.trim(),
			timestamp: null,
			status: null
		};

		// Deal with the timestamp mess.
		let year = creationDate.getUTCFullYear();
		const monthIndex = getMonthPT(dtHtml[0].innerText.split(" ")[1]);
		if (monthIndex < creationDate.getUTCMonth())
			year++;
		const timestamp = new Date(
			year,                                                // Year
			monthIndex,                                          // Month Index
			Number(dtHtml[0].innerText.split(" ")[0]),  // Day
			Number(dtHtml[1].innerText.split("h")[0]),  // Hours
			Number(dtHtml[1].innerText.split("h")[1])   // Minutes
		);
		update.timestamp = timestamp.toISOString();

		// Check for problems.
		if (!content.querySelector("[id*='Reason'] [data-expression]").classList.contains("display-container-none")) {
			update.status = {
				type: "issue",
				data: {
					description: content.querySelector("[id*='Reason'] [data-expression]").innerText.replace(/^Motivo:\s+/, "").trim()
				}
			};
		}

		// Check if it was delivered.
		if (update.title === "Entregue") {
			const recString = content.querySelector("[id*='FormatName'] [data-expression]").innerText.trim();
			update.status = {
				type: "delivered",
				data: {
					description: recString,
					to: recString.replace(/^Entregue\s+a:\s+/, "").trim()
				}
			};
		} else if (update.title === "Em entrega") {
			update.status = {
				type: "delivering",
				data: {
					description: update.description
				}
			};
		} else if ((update.title === "No ponto de entrega") &&
				update.description.includes("disponível para levantamento")) {
			const locString = content.querySelector("[id*='Location'] [data-expression]").innerText.trim();
			update.status = {
				type: "pickup",
				data: {
					description: locString,
					location: locString.split(" até ")[0],
					until: null
				}
			};

			// Calculate the until date.
			let until = timestamp;
			until.setUTCMonth(getMonthPT(locString.split(" até ")[1].split(" ")[1]),
				Number(locString.split(" até ")[1].split(" ")[0]));
			if (until.getUTCMonth() < timestamp.getUTCMonth())
				until.setUTCFullYear(until.getUTCFullYear() + 1);
			update.status.data.until = until.toISOString();
		} else if (update.title === "Aceite") {
			update.status = {
				type: "posted",
				data: {
					description: update.description
				}
			};
		} else if (update.title === "Aguarda entrada nos CTT") {
			update.status = {
				type: "created",
				data: {
					description: update.description,
					timestamp: creationDate.toISOString()
				}
			};
		}

		return update;
	};

	// Get easy label information.
	data.trackingCode = document.querySelector("[id*=ObjectCodeContainer] [data-expression]").innerText.trim();
	data.destination = {
		addressLine: null,
		city: document.querySelector("[data-block='TrackTrace.TT_ProductDestination_New'] [data-expression]").innerText.trim(),
		state: null,
		postalCode: null,
		country: null
	};

	// Get the package creation date.
	const creationDate = (function (dtString) {
		const match = dtString.trim().match(/(\d+) (\w+) (\d+), (\d+)h(\d+)/);
		return new Date(
			Number(match[3]),      // Year
			getMonthPT(match[2]),  // Month
			Number(match[1]),      // Day
			Number(match[4]),      // Hours
			Number(match[5])       // Minutes
		);
	})(document.querySelector("[data-block='TrackTrace.TT_ProductDetails'] [id*=ObjectCreation] [data-expression]").innerText);
	data.creationDate = creationDate.toISOString();

	// Parse the tracking history.
	const histItems = document.querySelectorAll("[data-block='TrackTrace.TT_Timeline_New'] [data-block='CustomerArea.AC_TimelineItemCustom']");
	histItems.forEach(function (item) {
		data.history.push(parseHistoryItem(item, creationDate));
	});

	// Set the current delivery status.
	if (data.history.length > 0)
		data.status = data.history[0].status;

	return data;
})();
