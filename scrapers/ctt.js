"use strict";

/**
 * Checks for errors shown in the tracking page.
 *
 * @returns {any|null} OpenParcel error object or null if there weren't any
 *                     errors.
 */
function errorCheck() {
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
				return OpenParcel.error.create(OpenParcel.error.codes.Blocked);
			}

			return OpenParcel.error.create(OpenParcel.error.codes.Unknown);
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
			return OpenParcel.error.create(OpenParcel.error.codes.ParcelNotFound);
		}

		return OpenParcel.error.create(OpenParcel.error.codes.Unknown);
	}

	return null;
}

/**
 * Performs the scraping operation.
 *
 * @return OpenParcel response object.
 */
function scrape() {
	let data = OpenParcel.data.create();

	// Check for errors, just in case.
	const error = errorCheck();
	if (error !== null)
		return error;

	// Get easy label information.
	data.trackingCode = document.querySelector("[id*=ObjectCodeContainer] [data-expression]").innerText.trim();
	data.destination = OpenParcel.data.createAddress({
		city: document.querySelector("[data-block='TrackTrace.TT_ProductDestination_New'] [data-expression]").innerText.trim()
	});

	// Get the package creation date.
	const creationDate = (function (dtString) {
		const match = dtString.trim().match(/(\d+) ([^ ]+) (\d+), (\d+)h(\d+)/);
		return new Date(
			Number(match[3]),      // Year
			OpenParcel.calendar.getMonthPT(match[2]),  // Month
			Number(match[1]),      // Day
			Number(match[4]),      // Hours
			Number(match[5])       // Minutes
		);
	})(document.querySelector("[data-block='TrackTrace.TT_ProductDetails'] [id*=ObjectCreation] [data-expression]").innerText);
	data.creationDate = creationDate.toISOString();

	// Parse the tracking history.
	const histItems = document.querySelectorAll("[data-block='TrackTrace.TT_Timeline_New'] [data-block='CustomerArea.AC_TimelineItemCustom']");
	histItems.forEach(function (item) {
		// Check if it's a disabled item.
		let title = item.querySelector("[id*=TimelineContent] [id*=Title] [data-expression]")
		if (!title.classList.value.includes("neutral")) {
			// Parse the item and push it to the history list.
			data.history.push(parseHistoryItem(item, creationDate));
		}
	});

	// Set the current delivery status.
	if (data.history.length > 0)
		data.status = data.history[0].status;

	return OpenParcel.data.finalTouches(data);
}

/**
 * Parses a tracking history item.
 *
 * @param {Element} item         HTML element of the update item block.
 * @param {Date}    creationDate Date of the creation of the tracking code.
 *
 * @returns OpenParcel tracking history item object.
 */
function parseHistoryItem(item, creationDate) {
	const content = item.querySelector("[id*=TimelineContent] [id*=Content]");
	const dtHtml = item.querySelectorAll("[id*=Left] [data-expression]");

	// Create the update object.
	const update = OpenParcel.data.createUpdate(
		item.querySelector("[id*=TimelineContent] [id*=Title] [data-expression]").innerText,
		content.querySelector("[id*='Event'] [data-expression]").innerText);

	// Get the update location.
	const upAddress = content.querySelector("[id*='Location'] [data-expression]").innerText;
	if ((upAddress.length > 0) && isNaN(Number(upAddress))) {
		update.location = OpenParcel.data.createAddress({
			addressLine: upAddress
		});
	}

	// Deal with the timestamp mess.
	let year = creationDate.getUTCFullYear();
	const monthIndex = OpenParcel.calendar.getMonthPT(dtHtml[0].innerText.split(" ")[1]);
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
		update.status = OpenParcel.data.createStatus("issue",
			content.querySelector("[id*='Reason'] [data-expression]").innerText.replace(/^Motivo:\s+/, "").trim());
	}

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
			location: OpenParcel.data.createAddress({
				addressLine: locString.split(" até ")[0]
			}),
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

	return update;
}
