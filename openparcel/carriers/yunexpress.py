#!/usr/bin/env python3

from DrissionPage.errors import WaitTimeoutError

from openparcel.carriers.base import BrowserBaseCarrier


class CarrierYunExpress(BrowserBaseCarrier):
    uid = 'yunexpress'
    name = 'YunExpress'
    tracking_url_base = 'https://www.yuntrack.com/parcelTracking?' \
                        'id=${tracking_code}'
    accent_color = '#04977A'

    def __init__(self, tracking_code: str = None):
        super().__init__(tracking_code)

    def fetch(self):
        try:
            # Load the page in the browser.
            self._fetch_page()

            try:
                # Wait for it to actually load something we can work with.
                self._wait_title_change('Tracking Results', timeout=8)
                elem_index = self._wait_page_complete([
                    '#timeline',
                    '.el-table__empty-block .el-table__empty-text .empty',
                    '.el-table .el-table_1_column_3 .el-tooltip.el-tag--info'],
                    timeout=10)

                # Check if we need to reload the page.
                if elem_index == 1:
                    self._disable_unload_script()
                    self.page.refresh()
                    self._wait_page_complete([
                        '#timeline',
                        '.el-table__empty-block .el-table__empty-text .empty',
                        '.el-table .el-table_1_column_3 .el-tooltip.el-tag--info'],
                        timeout=10)

                self._scrape_check_error()
            except WaitTimeoutError as e:
                self._scrape_check_error()
                raise e

            # Finally scrape it.
            self._scrape()
        finally:
            # Quit the browser.
            self._close_page()

        return self._resp_dict
