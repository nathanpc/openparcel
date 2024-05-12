/**
 * utils.js
 * Loads a set of utility functions that can be used by all scrapers.
 *
 * @author Nathan Campos <nathan@innoveworkshop.com>
 */

Object.assign(String.prototype, {
	/**
	 * Checks if a string contains any of the substrings in the array.
	 *
	 * @param {string[]} searchStrings Array of substrings to search for.
	 *
	 * @return {boolean} True if any of the strings was found. False otherwise.
	 */
    containsAny(searchStrings) {
		const str = this;
		return searchStrings.some(substring => str.includes(substring));
    }
});

/**
 * The main scraper and utility class of the project. Every carrier that is
 * implemented must inherit from this class.
 */
class OpenParcel {
	/**
	 * Constructs the scraper utility object.
	 */
	constructor() {
		this.parcel = new Parcel();
	}

	/**
	 * Scrapes the page for all the information about the parcel and its
	 * tracking history.
	 *
	 * @warning This method must be overwritten by the scraper script.
	 *
	 * @returns {Parcel | ParcelError} The parcel object with all the scraped
	 * information or an error object in case the proper stuff couldn't be
	 * found.
	 */
	scrape() {
		throw Error("scrape() method wasn't implemented for this carrier");
	}

	/**
	 * Scrapes the page for error messages and turns them into an object if they
	 * exist.
	 *
	 * @warning This method must be overwritten by the scraper script.
	 *
	 * @returns {ParcelError | null} Error object in case of a scraped message
	 * or null if no errors were found on the page.
	 */
	errorCheck() {
		throw Error("errorCheck() method wasn't implemented for this carrier");
	}

	/**
	 * Logs a message to our debugging log window in the web page. This is meant
	 * to assist us when we don't have access to the Developer Tools pane.
	 *
	 * @param {Object | String} obj       Object or message to be logged.
	 * @param {Boolean}         [newLine] Should we append a new line to the
	 *                                    message?
	 */
	static debugLog(obj, newLine = true) {
		// Check if our debug window is currently present.
		if (document.getElementById("openparcel-debugger") === null) {
			// Create the window.
			const root = document.createElement("div");
			root.id = "openparcel-debugger";
			root.style.cssText = "position: absolute; z-index: 9999; " +
				"height: 150px; width: 500px; top: 15px; left: 15px; " +
				"padding: 5px; background-color: whitesmoke; " +
				"border: 1px solid #c8c8c8;";

			// Create the console.
			const elem = document.createElement("textarea");
			elem.id = "op-console";
			elem.style.cssText = "width: 100%; height: 100%; font-size: 10pt; " +
				"font-family: monospace; box-sizing: border-box;";
			root.appendChild(elem);

			// Append it to the body.
			document.body.appendChild(root);
		}

		// Create the message to be logged.
		let msg;
		if (typeof obj === 'string' || obj instanceof String) {
			// It's just a string.
			msg = obj;
		} else {
			// It's an object. Convert it to a string and print it.
			msg = JSON.stringify(obj, undefined, 2);
		}

		// Print the message and append a newline if needed.
		const console = document.getElementById("op-console");
		if (newLine)
			msg += "\n";
		console.value += msg;
		console.scrollTop = 99999;
	}

	/**
	 * Drops (if needed) a token element in the page that can be used to check
	 * for major rewrites to the DOM in certain areas.
	 *
	 * @returns {HTMLDivElement} Our token element.
	 */
	static dropTokenElement() {
		// Get the token element.
		let elem = document.getElementById("op-token-elem");

		// Drop a new token element on the page if it doesn't exist.
		if (elem === null) {
			elem = document.createElement("div");
			elem.id = "op-token-elem";
			elem.innerText = "We are scraping you!";

			return document.body.appendChild(elem);
		}

		return elem;
	}

	/**
	 * Event handler for the notifications to the engine whenever there's an
	 * unload event.
	 *
	 * @param {BeforeUnloadEvent} event Before unload event.
	 *
	 * @see notifyUnload
	 * @see disableNotifyUnload
	 *
	 * @private
	 */
	static _notifyUnloadHandler(event) {
		/* Since this is deprecated Chrome will instead show a dialog that our
		   caller script receives as an empty string. */
		event.returnValue = 'REDIRECT';
	}

	/**
	 * Detects redirections from shitty web frameworks and notifies our engine
	 * whenever they happen.
	 */
	static notifyUnload() {
		window.addEventListener('beforeunload', OpenParcel._notifyUnloadHandler);
	}

	/**
	 * Disables the notifications to the engine whenever there's an unload
	 * event.
	 */
	static disableNotifyUnload() {
		window.removeEventListener('beforeunload', OpenParcel._notifyUnloadHandler);
	}

	/**
	 * Notifies the engine that an element has finally been loaded into the page
	 * by issuing an alert dialog box.
	 *
	 * @param {Array<String>} selectors Query selectors for elements to wait for.
	 */
	static notifyElementLoaded(selectors) {
		const observers = [];

		// Drop a token element to test for redirects or rewrites.
		const tokenElement = this.dropTokenElement();
		const tokenObserver = new MutationObserver(function (mutations) {
			OpenParcel.debugLog("Something touched our token element: ", false);
			OpenParcel.debugLog(mutations);
		});
		tokenObserver.observe(tokenElement, {
			childList: true,
			subtree: true,
			attributes: true
		});

		// Detect redirections from shitty web frameworks.
		OpenParcel.notifyUnload();

		// Check if something happened to our Python caller.
		if (selectors === null)
			throw new TypeError("Selectors to wait for must not be null");

		// Builds a list of browser error selectors.
		const browserErrorSelectors = [
			"#main-frame-error.interstitial-wrapper"
		];

		// Checks for our elements of interest.
		const checkForElements = function (elemSelectors, errorSelectors) {
			// Ensure no new iframes popped up.
			observeIframes();

			// Go through observers.
			for (const obs of observers) {
				// Go through querying the selectors of interest.
				for (let i = 0; i < elemSelectors.length; i++) {
					if (obs.parentDocument.querySelector(elemSelectors[i])) {
						// Log the fact that we got one.
						OpenParcel.debugLog("Selector found in page: " +
							elemSelectors[i]);

						// Disconnect all other observers.
						observers.forEach(function (obs) {
							OpenParcel.debugLog("Disconnecting observer: ",
								false);
							obs.observer.disconnect();
						});
						tokenObserver.disconnect();

						// Alert the parent script.
						alert("READY! (" + i + ")");
						return;
					}
				}

				// Should we check for browser errors as well?
				if ((errorSelectors === null) || ((obs.parentDocument !== document) &&
					(obs.elem !== document.body))) {
					continue;
				}

				// Go through querying the browser error selectors.
				for (let i = 0; i < errorSelectors.length; i++) {
					if (obs.parentDocument.querySelector(errorSelectors[i])) {
						// Log the fact that we got one.
						OpenParcel.debugLog("Error selector found: " +
							errorSelectors[i]);

						// Disconnect all other observers.
						observers.forEach(function (obs) {
							OpenParcel.debugLog("Disconnecting observer: ",
								false);
							obs.observer.disconnect();
						});
						tokenObserver.disconnect();

						// Alert the parent script.
						alert("READY! (" + -(i + 1) + ")");
						return;
					}
				}
			}
		};

		// Starts observing a body of interest.
		const startObserving = function (parentDocument, elem) {
			// Check if the element isn't already being observed.
			for (const item of observers) {
				if (item.elem === elem)
					return;
			}

			// Push our new observer into the observers array.
			observers.push({
				parentDocument: parentDocument,
				elem: elem,
				observer: new MutationObserver(function () {
					// Check if the element was found.
					checkForElements(selectors, browserErrorSelectors);
				})
			});

			// If you get "parameter 1 is not of type 'Node'" error, see
	        // https://stackoverflow.com/a/77855838/492336
			const obs = observers[observers.length - 1];
			obs.observer.observe(obs.elem, {
				childList: true,
				subtree: true
			});

			OpenParcel.debugLog("Started observing " +
				"<" + elem.tagName.toLowerCase() + " id=\"" + elem.id + "\" " +
				"class=\"" + elem.classList + "\">")
		};

		// Start observing all the iframes in the page as well.
		const observeIframes = function () {
			const iframes = document.getElementsByTagName("iframe");
			for (let i = 0; i < iframes.length; i++)
				startObserving(iframes[i].contentWindow.document,
					iframes[i].contentWindow.document.body);
		};

		// Observe changes in the DOM for our elements.
		startObserving(document, document.body);
		observeIframes();

		// Check if any of the elements are already in the document.
		checkForElements(selectors, browserErrorSelectors);
	}
}

/**
 * Abstraction of a parcel with all of its information and tracking history.
 */
class Parcel {
	/**
	 * Constructs the main parcel object for our API to return.
	 *
	 * @param {string}              trackingCode Parcel tracking code.
	 * @param {string}              trackingUrl  URL used to track this parcel.
	 * @param {ParcelTimestamp}     creationDate Date the parcel was created by the carrier.
	 * @param {ParcelLocation}      origin       Origin location of the parcel.
	 * @param {ParcelLocation}      destination  Final destination of the parcel.
	 * @param {ParcelETA}			eta			 Estimated time of arrival.
	 * @param {Array<ParcelUpdate>} history      Parcel tracking history.
	 */
	constructor(trackingCode = null, trackingUrl = window.location.href,
	            creationDate = null, origin = null, destination = null,
	            eta = null, history = []) {
		this.trackingCode = trackingCode;
		this.trackingUrl = trackingUrl;
		this.creationDate = creationDate;
		this.origin = origin;
		this.destination = destination;
		this.eta = eta;
		this.history = history;
	}

	/**
	 * Appends an older tracking history update item to the parcel history.
	 * Remember that the parcel history should be sorted by "newest first".
	 *
	 * @param {ParcelUpdate} update Older tracking history update item.
	 *
	 * @return New length of the history array.
	 */
	appendUpdate(update) {
		return this.history.push(update);
	}

	/**
	 * Creates a JSON representation of the object.
	 *
	 * @return JSON JSON representation of the object.
	 */
	toJSON() {
		const json = {
			trackingCode: this.trackingCode,
			trackingUrl: this.trackingUrl,
			creationDate: this.creationDate?.toString() ?? null,
			status: null,
			origin: this.origin?.toJSON() ?? null,
			destination: this.destination?.toJSON() ?? null,
			eta: this.eta?.toJSON() ?? null,
			history: []
		}

		// Set the current delivery status.
		if ((this.history.length > 0) && (this.history[0].status !== null))
			json.status = this.history[0].status.toJSON();

		// Populate the tracking history.
		for (const item of this.history)
			json.history.push(item.toJSON());

		return json;
	}
}

/**
 * Represents an update in the tracking history. Think of this as an item in the
 * timeline.
 */
class ParcelUpdate {
	/**
	 * Constructs a new tracking history update item.
	 *
	 * @param {string}          title         Main title of the update.
	 * @param {string}          [description] Detailed description of the update.
	 * @param {ParcelLocation}  [location]    Where the update occurred.
	 * @param {ParcelTimestamp} [timestamp]   When the update occurred.
	 * @param {ParcelStatus}    [status]      Additional and indexed information.
	 */
	constructor(title, description = null, location = null, timestamp = null,
	            status = null) {
		this.title = title;
		this.description = description;
		this.location = location;
		this.timestamp = timestamp;
		this.status = status;
	}

	/**
	 * Sets the update item timestamp.
	 *
	 * @param {Date} date Timestamp's date.
	 */
	setTimestamp(date) {
		this.timestamp = new ParcelTimestamp(date);
	}

	/**
	 * Creates a JSON representation of the object.
	 *
	 * @return JSON JSON representation of the object.
	 */
	toJSON() {
		return {
			title: this.title,
			description: this.description,
			location: this.location?.toJSON() ?? null,
			timestamp: this.timestamp?.toString() ?? null,
			status: this.status?.toJSON() ?? null
		};
	}
}

/**
 * Provides additional and indexable information about a parcel update.
 */
class ParcelStatus {
	/**
	 * Parcel status type enum.
	 */
	static Type = {
		Created: "created",
		Posted: "posted",
		InTransit: "in-transit",
		DepartedOrigin: "departed-origin",
		ArrivedDestination: "arrived-destination",
		CustomsCleared: "customs-cleared",
		DeliveryAttempt: "delivery-attempt",
		WaitingPickup: "pickup",
		Delivering: "delivering",
		Delivered: "delivered",
		Issue: "issue"
	};

	/**
	 * Constructs a new parcel status object.
	 *
	 * @param {Type}   type        Type of update status.
	 * @param {string} description Detailed description of this status.
	 * @param          [data]      Additional data/context.
	 */
	constructor(type, description, data = null) {
		this.type = type;
		this.description = description;
		this.data = data;

		// Ensure we have the required parameters for each status type.
		this.checkDataValid();
	}

	/**
	 * Checks if {@link data} contains all the required parameters given the
	 * type of the status.
	 */
	checkDataValid() {
		const base = this;

		// Checks if the data object has the required keys.
		const hasKeys = function (keys) {
			const errorString = `Parcel status ${base.type} does not contain ` +
				`some or any of the required keys: ${keys.join(", ")}`;

			// Check if we have nothing.
			if (base.data === null)
				throw Error(errorString);

			// Check if we have all the required keys.
			if (!Object.keys(base.data).every(key => keys.includes(key)))
				throw Error(errorString);
		};

		// Perform the checks based on the status type.
		switch (this.type) {
			case ParcelStatus.Type.Created:
				hasKeys(["timestamp"]);
				break;
			case ParcelStatus.Type.DepartedOrigin:
			case ParcelStatus.Type.ArrivedDestination:
				hasKeys(["location"]);
				break;
			case ParcelStatus.Type.WaitingPickup:
				hasKeys(["location", "until"]);
				break;
			case ParcelStatus.Type.Delivered:
				hasKeys(["to"]);
				break;
		}
	}

	/**
	 * Creates a JSON representation of the object.
	 *
	 * @return JSON JSON representation of the object.
	 */
	toJSON() {
		const json = {
			type: this.type,
			data: {
				description: this.description
			}
		}

		if (this.data !== null) {
			for (const key of Object.keys(this.data))
				json.data[key] = this.data[key];
		}

		return json;
	}
}

/**
 * Abstraction of a parcel's Estimated Time of Arrival (ETA).
 */
class ParcelETA {
	/**
	 * Constructs a parcel's estimated time of arrival object.
	 *
	 * @param {ParcelTimestamp} date		Day when the parcel will arrive.
	 * @param {string} 			[timeframe] Around when will the parcel arrive?
	 */
	constructor(date, timeframe = null) {
		this.date = date;
		this.timeframe = timeframe;
	}

	/**
	 * Creates a JSON representation of the object.
	 *
	 * @return JSON JSON representation of the object.
	 */
	toJSON() {
		return {
			date: this.date.toString(),
			timeframe: this.timeframe
		};
	}
}

/**
 * Worldwide location abstraction class.
 */
class ParcelLocation {
	/**
	 * Constructs a location object.
	 *
	 * @param {string} [addressLine] Address line of the location.
	 * @param {string} [city]        City.
	 * @param {string} [state]       State or district.
	 * @param {string} [postalCode]  Postal code.
	 * @param {string} [country]     Country.
	 */
	constructor(addressLine = null, city = null, state = null,
	            postalCode = null, country = null) {
		this.addressLine = addressLine;
		this.city = city;
		this.state = state;
		this.postalCode = postalCode;
		this.country = country;
		this.coords = {
			lat: null,
			lng: null
		};
	}

	/**
	 * Sets the location coordinates.
	 *
	 * @param lat Latitude value.
	 * @param lng Longitude value.
	 *
	 * @returns {ParcelLocation} The object itself for functional purposes.
	 */
	setCoords(lat, lng) {
		this.coords.lat = lat;
		this.coords.lng = lng;
		return this;
	}

	/**
	 * Creates a JSON representation of the object.
	 *
	 * @return JSON JSON representation of the object.
	 */
	toJSON() {
		const address = {
			addressLine: this.addressLine,
			city: this.city,
			state: this.state,
			postalCode: this.postalCode,
			country: this.country,
			searchQuery: null,
			coords: {
				lat: this.coords.lat,
				lng: this.coords.lng
			}
		};

		// Build the search query string.
		if ((address.coords.lat !== null) && (address.coords.lng !== null)) {
			// Based on geo coordinates.
			address.searchQuery = address.coords.lat + ", " +
				address.coords.lng;
		} else {
			// Based on bits of the address.
			address.searchQuery = " " + address.addressLine + "  " +
				address.city + "  " + address.state + "  " +
				address.postalCode + "  " + address.country + " ";
			address.searchQuery = address.searchQuery.replace(/\snull\s/g, " ");
			address.searchQuery = address.searchQuery.replace(/\s{2,}/g, " ");
			address.searchQuery = address.searchQuery.trim();
			if (address.searchQuery.length <= 1)
				address.searchQuery = null;
		}

		return address;
	}
}

/**
 * Abstracts away timestamps and how to represent them.
 */
class ParcelTimestamp {
	/**
	 * Constructs a timestamp abstraction object.
	 *
	 * @param {Date} date Date object of the timestamp.
	 */
	constructor(date = new Date()) {
		this.date = date;
	}

	/**
	 * Sets the time of our timestamp according to UTC.
	 *
	 * @param {number} hours   New hour of the day.
	 * @param {number} [min]   New minute of the hour.
	 * @param {number} [secs]  New second of the minute.
	 */
	setTime(hours, min = undefined, secs = undefined) {
		if (min === undefined) {
			this.date.setUTCHours(hours);
		} else if (secs === undefined) {
			this.date.setUTCHours(hours, min);
		} else {
			this.date.setUTCHours(hours, min, secs);
		}
	}

	/**
	 * Gets a month index based on a month's name. Can also take into account
	 * the langauge.
	 *
	 * @param {string} name Name of the month.
	 * @param {string} lang Language string: en, pt.
	 *
	 * @return {number} Month index.
	 */
	static getMonthIndex(name, lang = "en") {
		if (lang === "en") {
			// English
			switch (name) {
				case 'Jan':
				case 'January':
					return 0;
				case 'Feb':
				case 'February':
					return 1;
				case 'Mar':
				case 'March':
					return 2;
				case 'Apr':
				case 'April':
					return 3;
				case 'May':
					return 4;
				case 'Jun':
				case 'June':
					return 5;
				case 'Jul':
				case 'July':
					return 6;
				case 'Aug':
				case 'August':
					return 7;
				case 'Sep':
				case 'September':
					return 8;
				case 'Oct':
				case 'October':
					return 9;
				case 'Nov':
				case 'November':
					return 10;
				case 'Dec':
				case 'December':
					return 11;
				default:
					throw Error("Invalid english month name: " + name);
			}
		} else if (lang === "pt") {
			// Portuguese
			switch (name) {
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
				default:
					throw Error("Invalid portuguese month name: " + name);
			}
		}

		throw Error("Invalid language for parsing month name");
	}

	/**
	 * Creates a copy of this object.
	 *
	 * @return {ParcelTimestamp} The copy of the object.
	 */
	clone() {
		// Create a copy of our Date object.
		const dt = new Date();
		dt.setTime(this.date.getTime());

		// Create the copy of ourselves.
		return new ParcelTimestamp(dt);
	}

	/**
	 * Returns the timestamp in the standardized ISO 8601 format.
	 *
	 * @return {string} Timestamp in ISO 8601 format.
	 */
	toString() {
		return this.date.toISOString();
	}
}

/**
 * Error/exception abstraction object for our API.
 */
class ParcelError {
	/**
	 * Error code enum.
	 */
	static Code = {
		Unknown: {
			id: 0,
			name: "Unknown"
		},
		InvalidTrackingCode: {
			id: 1,
			name: "InvalidTrackingCode"
		},
		ParcelNotFound: {
			id: 2,
			name: "ParcelNotFound"
		},
		RateLimiting: {
			id: 3,
			name: "RateLimiting"
		},
		Blocked: {
			id: 4,
			name: "Blocked"
		},
		ProxyTimeout: {
			id: 5,
			name: "ProxyTimeout"
		},
		BrowserError: {
			id: 6,
			name: "BrowserError"
		}
	};

	/**
	 * Constructs a standard error object.
	 *
	 * @param {{name: string, id: number}} code   Error code description object.
	 * @param {JSON}                       [data] Extra data to be included.
	 */
	constructor(code, data= null) {
		this.code = code;
		this.data = data;
	}

	/**
	 * Creates a JSON representation of the object.
	 *
	 * @param {boolean} enclosed Should the returned object be enclosed in an
	 *                           error key?
	 *
	 * @return JSON JSON representation of the object.
	 */
	toJSON(enclosed = true) {
		const json = {
			error: {
				code: this.code,
				data: this.data
			}
		}

		return (enclosed) ? json : json.error;
	}
}
