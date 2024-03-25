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
	 * Waits for an element to exist.
	 *
	 * @param selector Query selector for the element to wait for.
	 *
	 * @returns {Promise<Element>} Promise of the loaded element.
	 */
	waitForElement(selector) {
		return new Promise(resolve => {
			if (document.querySelector(selector)) {
				return resolve(document.querySelector(selector));
			}

			const observer = new MutationObserver(mutations => {
				if (document.querySelector(selector)) {
					observer.disconnect();
					resolve(document.querySelector(selector));
				}
			});

			// If you get "parameter 1 is not of type 'Node'" error, see
	        // https://stackoverflow.com/a/77855838/492336
			observer.observe(document.body, {
				childList: true,
				subtree: true
			});
		});
	},

	/**
	 * Notifies the engine that an element has finally been loaded into the page.
	 *
	 * @param selector Query selector for the element to wait for.
	 */
	notifyElementLoaded(selector) {
	    this.waitForElement(selector).then(function (elem) {
	        alert("READY!");
	    });
	}
};
