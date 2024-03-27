/**
 * utils.js
 * Loads a set of utility functions that can be used by all scrapers.
 *
 * @author Nathan Campos <nathan@innoveworkshop.com>
 */

"use strict";

window.OpenParcel = {
	data: {
		/**
		 * Creates a brand new data object.
		 *
		 * @returns {{trackingUrl: string, origin: {country: string|null,
		 *           city: string|null, postalCode: string|null,
		 *           state: string|null, addressLine: string|null,
		 *           coords: {lat: Number|null, lng: Number|null}}|null,
		 *           destination: {country: string|null, city: string|null,
		 *           postalCode: string|null, state: string|null,
		 *           addressLine: string|null, coords: {lat: Number|null,
		 *           lng: Number|null}}|null, trackingCode: string,
		 *           history: *[], creationDate: string,
		 *           status: {data: {description: string}, type: string}}}
		 */
		create() {
			return {
				trackingCode: null,
				trackingUrl: window.location.href,
				creationDate: null,
				status: null,
				origin: null,
				destination: null,
				history: []
			};
		},

		/**
		 * Creates a brand new tracking history update object.
		 *
		 * @param {string}      title       Very brief description.
		 * @param {string|null} description Detailed description.
		 * @param               [info]      Optional properties of the object.
		 *
		 * @returns {{description: string|null, location: {country: string|null,
		 *           city: string|null, postalCode: string|null,
		 *           state: string|null, addressLine: string|null,
		 *           coords: {lat: Number|null, lng: Number|null}},
		 *           title: string, timestamp: string, status: null}}
		 *          OpenParcel tracking history update object.
		 */
		createUpdate(title, description, info) {
			const update = {
				title: title,
				description: description,
				location: null,
				timestamp: null,
				status: null
			};

			// Set some of the properties.
			if (info !== undefined) {
				Object.keys(info).forEach(function (key) {
					update[key] = info[key];
				});
			}

			return update;
		},

		/**
		 * Creates a brand new data status object.
		 *
		 * @param {string} type        Status type.
		 * @param {string} description Brief description.
		 * @param          [data]      Additional data fields.
		 *
		 * @returns {{type: string, data: {description: string}}}
		 *          OpenParcel data status object.
		 */
		createStatus(type, description, data) {
			const status = {
				type: type,
				data: {
					description: description
				}
			};

			// Append additional data.
			if (data !== undefined) {
				Object.keys(data).forEach(function (key) {
					status.data[key] = data[key];
				});
			}

			return status;
		},

		/**
		 * Creates a brand new address object.
		 *
		 * @param [info] Information to be populated into the address object.
		 *
		 * @returns {{country: string|null, city: string|null,
		 *           postalCode: string|null, state: string|null,
		 *           addressLine: string|null, coords: {lat: Number|null,
		 *           lng: Number|null}}}
		 *          OpenParcel address object.
		 */
		createAddress(info) {
			const address = {
				addressLine: null,
				city: null,
				state: null,
				postalCode: null,
				country: null,
				searchQuery: null,
				coords: {
					lat: null,
					lng: null
				}
			};

			// Set some of the properties.
			if (info !== undefined) {
				Object.keys(info).forEach(function (key) {
					address[key] = info[key];
				});
			}

			return address;
		},

		/**
		 * Applies some final touches to the data object before it's returned to
		 * the server.
		 *
		 * @param           data        OpenParcel data object to be treated.
		 * @param {boolean} [forceSort] Should we forcefully sort the history?
		 *
		 * @return Properly prepared OpenParcel data object for the server.
		 */
		finalTouches(data, forceSort) {
			if ((forceSort !== undefined) && forceSort) {
				// Ensure the history is ordered from newest to oldest.
				data.history.sort(function (a, b) {
					return (new Date(b.timestamp).getTime()) -
						(new Date(a.timestamp).getTime());
				});
			}

			// Fix addresses in the data object.
			OpenParcel.data.fixAddress(data.origin);
			OpenParcel.data.fixAddress(data.destination);
			data.history.forEach(function (update) {
				OpenParcel.data.fixAddress(update.location);
			});

			return data;
		},

		/**
		 * Builds the query string for an address object and fixes any
		 * abnormalities.
		 *
		 * @param {{country: string|null, city: string|null,
		 *         postalCode: string|null, state: string|null,
		 *         addressLine: string|null, coords: {lat: Number|null,
		 *         lng: Number|null}, queryString: string|null}} address
		 */
		fixAddress (address) {
			if (address === null)
				return;

			// Build the search query string based on geo coordinates.
			if ((address.coords.lat !== null) && (address.coords.lng !== null)) {
				address.searchQuery = address.coords.lat + ", " +
					address.coords.lng;
				return;
			}

			// Build the search query string based on bits of the address.
			address.searchQuery = " " + address.addressLine + "  " +
				address.city + "  " + address.state + "  " +
				address.postalCode + "  " + address.country + " ";
			address.searchQuery = address.searchQuery.replace(/\snull\s/g, " ");
			address.searchQuery = address.searchQuery.replace(/\s{2,}/g, " ");
			address.searchQuery = address.searchQuery.trim();
			if (address.searchQuery.length <= 1)
				address.searchQuery = null;
		}
	},

	error: {
		codes: {
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
			}
		},

		/**
		 * Generates a standard error object.
		 *
		 * @param {{id: number, name: string}} code   Error code description object.
		 * @param {any}                        [data] Extra data to be included.
		 *
		 * @returns {{error: {code: {id: number, name: string}, data: (*|null)}}}
		 */
		create(code, data) {
			return {
				error: {
					code: code,
					data: (data !== undefined) ? data : null
				}
			}
		}
	},

	calendar: {
		getMonth(monthName) {
			switch (monthName) {
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
			}
		},
		getMonthPT(monthName) {
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
		}
	},

	/**
	 * Logs a message to our debugging log window in the web page. This is meant
	 * to assist us when we don't have access to the Developer Tools pane.
	 *
	 * @param obj {Object|String} Object or message to be logged.
	 * @param [newLine] {Boolean} Should we append a new line to the message?
	 */
	debugLog(obj, newLine = true) {
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
		let msg = "";
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
	},

	dropTokenElement() {
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
	},

	/**
	 * Notifies the engine that an element has finally been loaded into the page.
	 *
	 * @param selectors {Array<String>} Query selectors for elements to wait for.
	 */
	notifyElementLoaded(selectors) {
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
		window.addEventListener('beforeunload', (event) => {
			/* Since this is deprecated Chrome will instead show a dialog that
			   our caller script receives as an empty string. */
			event.returnValue = 'REDIRECT';
		});

		// Check if something happened to our Python caller.
		if (selectors === null)
			throw new TypeError("Selectors to wait for must not be null");

		// Checks for our elements of interest.
		const checkForElements = function () {
			// Ensure no new iframes popped up.
			observeIframes();

			// Go through observers.
			for (const obs of observers) {
				// Go through querying the selectors of interest.
				for (let i = 0; i < selectors.length; i++) {
					if (obs.parentDocument.querySelector(selectors[i])) {
						// Log the fact that we got one.
						OpenParcel.debugLog("Selector found in page: " +
							selectors[i]);

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
					checkForElements();
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
		checkForElements();
	}
};
