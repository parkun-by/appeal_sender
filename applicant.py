import json
import logging
import time
from typing import Callable, Tuple

import requests
from selenium import webdriver
from selenium.common.exceptions import ElementClickInterceptedException

import config
import emailer
from browser import create_window
from exceptions import BrowserError, RancidAppeal
from waiter import wait_decorator

logger = logging.getLogger(__name__)


class Applicant:
    def __init__(self):
        self.mailbox = emailer.Emailer()
        self.browser = None

    def make_visible(self, element, browser: webdriver.Remote) -> None:
        # returns dict of X, Y coordinates
        coordinates = element.location_once_scrolled_into_view

        browser.execute_script(
            f'window.scrollTo({coordinates["x"]}, {coordinates["y"]});')

    def _extract_status_captcha(self, element) -> Tuple[str, str]:
        text = element.text.lower()

        logger.info(f'_extract_status_captcha - {text}')

        if text == 'неверный ответ':
            return config.WRONG_INPUT, text
        elif 'выслано письмо со ссылкой' in text:
            return config.OK, text
        else:
            return config.FAIL, text

    def _extract_status_sending(self, element) -> Tuple[str, str]:
        text = element.text.lower().strip()

        logger.info(f'_extract_status_sending - {text}')

        if 'ваше обращение отправлено' in text:
            return config.OK, text
        else:
            # self.browser.save_screenshot('extract_status_sending.png')
            return config.FAIL, text

    def _extract_status_appeal(self, element) -> Tuple[str, str]:
        text = element.text.lower().strip()
        logger.info(f'_extract_status_appeal - {text}')
        return config.OK, text

    def _upload_captcha(self, browser: webdriver.Remote) -> str:
        captcha = self._get_element_by_xpath(
            '//div[@class="col-sm-6"]/div[2]/*[name()="svg"]', browser)

        upload_url = 'https://telegra.ph/upload'
        files = {'file': ('file', captcha.screenshot_as_png, 'image/png')}
        result = requests.post(upload_url, files=files).json()
        logger.info("Нашли урл капчи")
        return f'https://telegra.ph{result[0]["src"]}'

    def enter_captcha_and_submit(self,
                                 captcha_text: str,
                                 browser: webdriver.Remote) -> str:
        captcha_field = self._get_element_by_id("captcha", browser)
        self.make_visible(captcha_field, browser)
        self._fill_field(captcha_field, captcha_text)

        submit_button_xpath = \
            '//div[@class="col-sm-6"]/button[contains(@class, "md-primary")]'

        self.click_button(submit_button_xpath,
                          '//div[@id="info-message"]/p',
                          browser)

        logger.info("Нажали сабмит капчи")

        submit_status, status_text = self.get_popup_info(
            self._extract_status_captcha, browser)

        logger.info(f'Достали статус {status_text}')

        if submit_status == config.WRONG_INPUT:
            # self.browser.save_screenshot('WRONG_INPUT.png')
            status = config.WRONG_INPUT
        elif submit_status != config.OK:
            # self.browser.save_screenshot('FAIL.png')
            status = config.FAIL
        else:
            status = config.OK

        return status

    def _get_captcha_site(self, email: str, browser: webdriver.Remote) -> None:
        browser.get(f'{config.POLICE_URL}/ru/electronicAppealLogin')

        email_field = self._get_element_by_id("email", browser)
        self.make_visible(email_field, browser)
        self._fill_field(email_field, email)
        logger.info("Заполнили емаил")

        rules_acception = self._get_element_by_class("md-container", browser)
        self.make_visible(rules_acception, browser)
        rules_acception.click()
        logger.info("Кликнули на галку")

    def get_appeal_url(self, email: str, password: str) -> str:
        return self.mailbox.get_appeal_url(email, password)

    def _fill_field(self, field, text):
        logger.info('Заполняем поле')
        try:
            field.send_keys(text)
        except Exception as exc:
            logger.info(f'ОЙ _fill_field - {str(exc)}')
            logger.exception(exc)
            field.send_keys(text)

    @wait_decorator(Exception, pause=0.5, exception_to_raise=BrowserError)
    def _get_element_by_class(self,
                              element_class: str,
                              browser: webdriver.Remote):
        return browser.find_element_by_class_name(element_class)

    @wait_decorator(Exception, pause=0.5, exception_to_raise=BrowserError)
    def _get_element_by_id(self, element_id: str, browser: webdriver.Remote):
        return browser.find_element_by_id(element_id)

    @wait_decorator(Exception, pause=0.5, exception_to_raise=BrowserError)
    def _get_element_by_xpath(self, xpath: str, browser: webdriver.Remote):
        return browser.find_element_by_xpath(xpath)

    @wait_decorator(ElementClickInterceptedException)
    def get_png_captcha(self, email: str, browser: webdriver.Remote) -> str:
        create_window(browser)
        self._get_captcha_site(email, browser)
        logger.info("Загрузили сайт с капчей")
        return self._upload_captcha(browser)

    @wait_decorator(ElementClickInterceptedException)
    def get_svg_captcha(self, email: str, browser: webdriver.Remote) -> str:
        create_window(browser)
        self._get_captcha_site(email, browser)
        logger.info("Загрузили сайт с капчей")
        return self._get_captcha_svg(browser)

    def _get_captcha_svg(self, browser: webdriver.Remote) -> str:
        web_elements = browser.find_elements_by_xpath(
            '//div[@class="col-sm-6"]/div[2]/*[name()="svg"]/*[name()="path"]')

        html_elements = map(lambda element: element.get_attribute('outerHTML'),
                            web_elements)

        purified_svg_elements = filter(
            lambda element: 'fill="none"' not in element,
            html_elements)

        svg_image = ""
        svg_image += ('<svg xmlns="http://www.w3.org/2000/svg" ' +
                      'width="150" height="50" viewBox="0,0,150,50">')
        for element in purified_svg_elements:
            svg_image += element
        svg_image += "</svg>"

        return svg_image

    @wait_decorator(ElementClickInterceptedException)
    def send_appeal(self,
                    data: dict,
                    url: str,
                    browser: webdriver.Remote) -> tuple:
        try:
            create_window(browser)
            browser.get(url)
            logger.info("Загрузили сайт с формой обращения")

            last_name_field = self._get_element_by_xpath(
                '//input[@data-ng-model="appeal.last_name"]',
                browser)

            self.make_visible(last_name_field, browser)
            self._fill_field(last_name_field, data['sender_last_name'])

            logger.info("Ввели фамилию")

            first_name_field = self._get_element_by_xpath(
                '//input[@data-ng-model="appeal.first_name"]',
                browser)

            self.make_visible(first_name_field, browser)
            self._fill_field(first_name_field, data['sender_first_name'])

            logger.info("Ввели имя")

            patronymic_name_field = self._get_element_by_xpath(
                '//input[@ng-model="appeal.middle_name"]',
                browser)

            self.make_visible(patronymic_name_field, browser)
            self._fill_field(patronymic_name_field, data['sender_patronymic'])

            logger.info("Ввели отчество")

            division_select_field_xpath = \
                '//md-select[@ng-model="appeal.division"]'

            division_xpath = '//div[@id="select_container_10"]/' + \
                'md-select-menu/md-content/' + \
                'md-option[starts-with(@id,"select_option_")]/' + \
                f'div[@class="md-text"]/span[.="{data["police_department"]}"]'

            self.click_button(division_select_field_xpath,
                              division_xpath,
                              browser,
                              ElementClickInterceptedException)

            subdivision_select_field_xpath = \
                '//md-select[@ng-model="appeal.subdivision"]'

            self.click_button(division_xpath,
                              subdivision_select_field_xpath,
                              browser)

            zipcode_xpath = '//input[@ng-model="appeal.postal_code"]'

            if data['police_subdepartment']:
                subdivision_xpath = '//div[@id="select_container_12"]/' + \
                    'md-select-menu/md-content/' + \
                    'md-option[starts-with(@id,"select_option_")]/' + \
                    f'div[@class="md-text"]/' + \
                    f'span[.="{data["police_subdepartment"]}"]'

                self.click_button(subdivision_select_field_xpath,
                                  subdivision_xpath,
                                  browser,
                                  ElementClickInterceptedException)

                self.click_button(subdivision_xpath, zipcode_xpath, browser)

            logger.info("Выбрали отдел ГУВД")

            zipcode = self._get_element_by_xpath(zipcode_xpath, browser)
            self.make_visible(zipcode, browser)
            self._fill_field(zipcode, data['sender_zipcode'])

            logger.info("Ввели индекс")

            city = self._get_element_by_xpath(
                '//input[@ng-model="appeal.city"]', browser)

            self.make_visible(city, browser)
            self._fill_field(city, data['sender_city'])

            logger.info("Ввели город")

            street = self._get_element_by_xpath(
                '//input[@ng-model="appeal.street"]', browser)

            self.make_visible(street, browser)
            self._fill_field(street, data['sender_street'])

            logger.info("Ввели улицу")

            building = self._get_element_by_xpath(
                '//input[@ng-model="appeal.house"]', browser)

            self.make_visible(building, browser)
            self._fill_field(building, data['sender_house'])

            logger.info("Ввели дом")

            block = self._get_element_by_xpath(
                '//input[@ng-model="appeal.korpus"]', browser)

            self.make_visible(block, browser)
            self._fill_field(block, data['sender_block'])

            logger.info("Ввели корпус")

            flat = self._get_element_by_xpath(
                '//input[@ng-model="appeal.flat"]', browser)

            self.make_visible(flat, browser)
            self._fill_field(flat, data['sender_flat'])

            logger.info("Ввели квартиру")

            text = self._get_element_by_xpath(
                '//textarea[@ng-model="appeal.text"]', browser)

            self.make_visible(text, browser)

            self.enter_appeal('//textarea[@ng-model="appeal.text"]',
                              data['text'],
                              browser)

            self._fill_field(text, " ")

            logger.info("Ввели текст")

            self.attach_photos(data['violation_photo_files_paths'], browser)

            submit_button_xpath = '//div[@class="col-sm-6 text-center"]/' + \
                                  'button[contains(@class, "md-primary")]'

            if config.ALLOW_SENDING:
                self.click_button(submit_button_xpath,
                                  '//div[@id="info-message"]/p',
                                  browser)

                logger.info("Отправили")

                submit_status, status_text = self.get_popup_info(
                    self._extract_status_sending, browser)

                if submit_status != config.OK:
                    return config.FAIL, status_text
        except ElementClickInterceptedException as exc:
            # let's try to get error message
            status, status_text = self.get_popup_info(
                self._extract_status_appeal,
                browser,
                max_attempts=6)

            if status == config.OK:
                logger.info(status_text)
                raise RancidAppeal

            raise exc
        except Exception as exc:
            logger.info(f'ОЙ send_appeal - {str(exc)}')
            logger.exception(exc)
            return config.FAIL, str(exc)

        logger.info("Успех")
        return config.OK, ''

    def click_button(self, button_xpath: str,
                     next_elem_xpath: str,
                     browser: webdriver.Remote,
                     exc=None):
        sended = False
        tries = 5

        while not sended:
            try:
                button = self._get_element_by_xpath(button_xpath, browser)
                self.make_visible(button, browser)
                button.click()
                self._get_element_by_xpath(next_elem_xpath, browser)
                sended = True
            except Exception:
                logger.exception("click_button")

                if tries:
                    sended = False
                    tries -= 1
                else:
                    if exc:
                        raise exc
                    else:
                        sended = True

    @wait_decorator(Exception, pause=0.5, exception_to_raise=BrowserError)
    def enter_appeal(self,
                     xpath: str,
                     appeal_text: str,
                     browser: webdriver.Remote):
        text_for_js = json.dumps(appeal_text, ensure_ascii=False)

        browser.execute_script(
            f'document.getElementById("input_20").value={text_for_js};')

    def get_popup_info(self,
                       extractor: Callable,
                       browser: webdriver.Remote,
                       max_attempts: int = 15) -> Tuple[str, str]:
        text = ''
        counter = 0
        infobox = None

        while not text:
            logger.info(f'Попытка взять текст попапа {counter}')

            if counter > max_attempts:
                logger.error('Нет попапа')
                browser.save_screenshot(
                    '/tmp/temp_files_parkun/get_popup_info_error.png')
                raise BrowserError

            try:
                infobox = self._get_element_by_xpath(
                    '//div[@id="info-message"]/p', browser)
            except Exception:
                browser.save_screenshot(
                    '/tmp/temp_files_parkun/get_popup_info_error1.png')
                logger.exception("get_popup_info exc")

            text = infobox.text.strip()
            counter += 1
            time.sleep(2)

        return extractor(infobox)

    def attach_photos(self, photo_paths: list,
                      browser: webdriver.Remote) -> None:
        attach_field = self._get_element_by_xpath("//input[@type=\"file\"]",
                                                  browser)

        label = attach_field.find_element_by_xpath("./..")

        js = "arguments[0].style.height='100px'; \
            arguments[0].style.width='100px'; \
            arguments[0].style.overflow='visible'; \
            arguments[0].style.visibility='visible'; \
            arguments[0].style.opacity = 1"

        browser.execute_script(js, label)

        for path in photo_paths:
            try:
                self._fill_field(attach_field, path)
            except Exception as exc:
                logger.info(f'Фотка не прикрепляется {path} - {str(exc)}')

        logger.info("Прикрепили файлы")
