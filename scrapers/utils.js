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
		 *           state: string|null, addressLine: string|null}|null,
		 *           destination: {country: string|null, city: string|null,
		 *           postalCode: string|null, state: string|null,
		 *           addressLine: string|null}|null, trackingCode: string,
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
		 *           state: string|null, addressLine: string|null},
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
		 *           addressLine: string|null}}
		 *          OpenParcel address object.
		 */
		createAddress(info) {
			const address = {
				addressLine: null,
				city: null,
				state: null,
				postalCode: null,
				country: null
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
		 * @param data OpenParcel data object to be treated.
		 *
		 * @return Properly prepared OpenParcel data object for the server.
		 */
		finalTouches(data) {
			// Ensure the history is ordered from newest to oldest.
			data.history.sort(function (a, b) {
				return (new Date(b.timestamp).getTime()) -
					(new Date(a.timestamp).getTime());
			});

			return data;
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
