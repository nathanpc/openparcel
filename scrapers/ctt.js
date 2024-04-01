class Carrier extends OpenParcel {
	errorCheck() {
		// Handle errors that appear in the feedback popup message object.
		const fbMessageContainer = document.querySelector("#feedbackMessageContainer");
		if (fbMessageContainer !== null) {
			const fbMessageText = fbMessageContainer.querySelector(".feedback-message-text");
			if (fbMessageText !== null) {
				const errMessage = fbMessageText.innerText;

				// Check if we have been blocked (same message as rate limiting).
				if (errMessage.includes("Atingiu o limite")) {
					// Message: "Atingiu o limite permitido para pesquisas de objetos.
					// Por favor, tente mais tarde"
					return new ParcelError(ParcelError.Code.Blocked);
				}

				return new ParcelError(ParcelError.Code.Unknown);
			}
		}

		// Handle errors that appear in the error message block object.
		const errBlockSelector = "[data-block='TrackTrace.TT_ObjectErrorCard']";
		let errBlock = document.querySelector(errBlockSelector);
		if (errBlock === null) {
			// Errors may appear in a specific iframe.
			const iframe = document.querySelector("iframe[id*=objectSearchFrame]");
			if (iframe !== null)
				errBlock = iframe.contentWindow.document.querySelector(errBlockSelector);
		}
		if (errBlock !== null) {
			const errMessage = errBlock.querySelector("[id*='Content'] [data-expression]").innerText;

			if (errMessage.includes("não foi encontrado")) {
				return new ParcelError(ParcelError.Code.ParcelNotFound);
			}

			return new ParcelError(ParcelError.Code.Unknown);
		}

		return null;
	}

	scrape() {
		const base = this;

		// Check for errors, just in case.
		const error = this.errorCheck();
		if (error !== null)
			return error;

		// Get easy label information.
		this.parcel.trackingCode = document.querySelector(
			"[id*=ObjectCodeContainer] [data-expression]").innerText.trim();
		this.parcel.destination = new ParcelLocation(null, document.querySelector(
			"[data-block='TrackTrace.TT_ProductDestination_New'] [data-expression]")
			.innerText.trim());

		// Get the package creation date.
		this.parcel.creationDate = (function (dtString) {
			const match = dtString.trim().match(/(\d+) ([^ ]+) (\d+), (\d+)h(\d+)/);
			return new ParcelTimestamp(new Date(
				Number(match[3]),      // Year
				ParcelTimestamp.getMonthIndex(match[2], "pt"),  // Month
				Number(match[1]),      // Day
				Number(match[4]),      // Hours
				Number(match[5])       // Minutes
			));
		})(document.querySelector(
			"[data-block='TrackTrace.TT_ProductDetails'] [id*=ObjectCreation] [data-expression]")
			.innerText);

		// Parse the tracking history.
		const histItems = document.querySelectorAll(
			"[data-block='TrackTrace.TT_Timeline_New'] [data-block='CustomerArea.AC_TimelineItemCustom']");
		histItems.forEach(function (item) {
			// Check if it's a disabled item.
			let title = item.querySelector(
				"[id*=TimelineContent] [id*=Title] [data-expression]")
			if (!title.classList.value.includes("neutral")) {
				// Parse the item and push it to the history list.
				base.parcel.appendUpdate(base.parseHistoryItem(item,
					base.parcel.creationDate));
			}
		});

		return this.parcel;
	}

	/**
	 * Parses a tracking history item.
	 *
	 * @param {Element}         item         HTML element of the update item block.
	 * @param {ParcelTimestamp} creationDate Date of the creation of the tracking code.
	 *
	 * @returns {ParcelUpdate} OpenParcel tracking history item object.
	 */
	parseHistoryItem(item, creationDate) {
		const content = item.querySelector("[id*=TimelineContent] [id*=Content]");
		const dtHtml = item.querySelectorAll("[id*=Left] [data-expression]");

		// Create the update object.
		const update = new ParcelUpdate(
			item.querySelector("[id*=TimelineContent] [id*=Title] [data-expression]").innerText,
			content.querySelector("[id*='Event'] [data-expression]").innerText);

		// Get the update location.
		const address = content.querySelector("[id*='Location'] [data-expression]").innerText;
		if ((address.length > 0) && isNaN(Number(address)))
			update.location = new ParcelLocation(address);

		// Deal with the timestamp mess and detect if a date is in fact in the past.
		let year = creationDate.date.getUTCFullYear();
		const monthIndex = ParcelTimestamp.getMonthIndex(
			dtHtml[0].innerText.split(" ")[1], "pt");
		if (monthIndex < creationDate.date.getUTCMonth())
			year++;
		update.timestamp = new ParcelTimestamp(new Date(
			year,                                       // Year
			monthIndex,                                 // Month Index
			Number(dtHtml[0].innerText.split(" ")[0]),  // Day
			Number(dtHtml[1].innerText.split("h")[0]),  // Hours
			Number(dtHtml[1].innerText.split("h")[1])   // Minutes
		));

		// Check for problems.
		if (!content.querySelector("[id*='Reason'] [data-expression]").classList
				.contains("display-container-none")) {
			update.status = new ParcelStatus(
				ParcelStatus.Type.Issue,
				content.querySelector("[id*='Reason'] [data-expression]").innerText
					.replace(/^Motivo:\s+/, "").trim()
			);
		}

		// Check if it was delivered.
		if (update.title === "Entregue") {
			const recString = content.querySelector(
				"[id*='FormatName'] [data-expression]").innerText.trim();
			update.status = new ParcelStatus(ParcelStatus.Type.Delivered, recString, {
				to: recString.replace(/^Entregue\s+a:\s+/, "").trim()
			});
		} else if (update.title === "Em entrega") {
			update.status = new ParcelStatus(ParcelStatus.Type.Delivering,
				update.description);
		} else if ((update.title === "No ponto de entrega") &&
				update.description.includes("disponível para levantamento")) {
			const locString = content.querySelector(
				"[id*='Location'] [data-expression]").innerText.trim();
			update.status = new ParcelStatus(ParcelStatus.Type.WaitingPickup, locString, {
				location: new ParcelLocation(locString.split(" até ")[0]),
				until: null
			});

			// Calculate the until date.
			let until = update.timestamp.clone();
			until.date.setUTCMonth(
				ParcelTimestamp.getMonthIndex(
					locString.split(" até ")[1].split(" ")[1], "pt"),
				Number(locString.split(" até ")[1].split(" ")[0]));
			if (until.date.getUTCMonth() < update.timestamp.date.getUTCMonth())
				until.date.setUTCFullYear(until.date.getUTCFullYear() + 1);
			update.status.data.until = until.toString();
		} else if (update.title === "Aceite") {
			update.status = new ParcelStatus(ParcelStatus.Type.Posted,
				update.description);
		} else if (update.title === "Aguarda entrada nos CTT") {
			update.status = new ParcelStatus(ParcelStatus.Type.Created, update.description, {
				timestamp: creationDate.toString()
			});
		}

		return update;
	}
}
