#!/usr/bin/env python3
# vim: set ts=4 fileencoding=UTF-8 :
#

import getpass
import json
import logging
from uuid import uuid4
from ws4py.client import WebSocketBaseClient
from ws4py.messaging import Message

log = logging.getLogger("p24-client")


class P24Session():
    ''' Хранит данные клиентской сессии '''

    def __init__(self):
        self.JSESSIONID = None
        self.skey = None
        self.ekbToken = None


class P24Authenticator(WebSocketBaseClient):
    ''' Контролирует процесс аутентификации в Приват24. '''

    def __init__(self, wsurl = 'wss://www.privat24.ua/ws/sr'):
       super().__init__(wsurl)
       self.sid = None
       self.fingerprint = uuid4().hex
       self.auth_frontend = SimpleAuthFrontend()

    def authenticate(self, login:str, password:str, auth_frontend = None):
        self.login = login
        self.password = password
        self.connect()
        self.send('{"cmd": "init", "data": {"referrer": "https://privat24.privatbank.ua/p24/news"}}')
        self.run()
        self.password = None
        return P24Session()

    def _send_form(self, form:str, data:dict):
        msg = {
                'cmd': form,
                'fingerprint': self.fingerprint,
                'sid': self.sid,
                'data': { 'fingerprint': self.fingerprint }
        }
        msg['data'].update(data)
        self.send(json.dumps(msg))

    @staticmethod 
    def check_msg_error(message):
        ''' Проверка не является ли пришедшее сообщение - сообщением об ошибке.
            Если да - генерируем исключение.
        '''
        if 'msg' not in message or not isinstance(message['msg'], dict):
            return
        if message['msg']['type'] == 'error':
            raise RuntimeError('Auth process error', message['msg'])

    def received_message(self, message:Message):
        log.debug('Recive: %s', message)
        assert message.is_text
        msg = json.loads(str(message))

        self.check_msg_error(msg)

        if 'cmd' in msg:
            cmd = msg['cmd']
            log.debug(cmd)
            if cmd == 'show_login_phone_form':             # Step 2: Phone form
                if msg['qr_code'] != 'null':
                    self._send_form(cmd, {'phone': self.login })
            elif cmd == 'show_static_password_form':       # Step 3: Password form
                self._send_form(cmd, {
                    'static_password': self.password,
                    'asLegalPersone': False                # true - business, false - physical
                    })

            elif cmd == 'show_otp_password_form':
                log.warn('Otp password form: %s', msg)

            elif cmd == 'show_sms_password_form':
                log.info('Sms confirmation requested')
                smspass = self.auth_frontend.query_sms_password()
                self._send_form(cmd, { 'sms_password': smspass })

            elif cmd == 'show_pin_cards_form':             # Форма запроса pin кода карты
                log.info('Pin cards form :(')
                raise RuntimeError('Card PIN not supported')

            elif cmd == 'show_ivr_form':                   # Банк звонит на телефон
                log.info('Bank call to you phone')
                #raise RuntimeError('Bank call not supported')

            elif cmd == 'show_ivr_captcha_form':           # Клиенту нужно позвонить на указанный банком телефон
                log.info('Bank request callback')
                self.auth_frontend.ivr_callback(msg['data']['phone'], msg['msg']['text'])

            elif cmd == 'redirect':                        # Аутентификация успешна, пришел redirect
                url = msg['data']['redirect_url']
                log.info('Auth successfull. Redirect to: %s', url)
                self.close()

            else:
                log.warn('Unknown command %s', cmd)

        elif 'init_result' in msg:                         # Step 1: Init success
            assert msg['init_result'] == 'ok'
            self.sid = msg['sid']
        elif 'show_login_phone_form_result' in msg:        # Step 2.1: Phone ok
            assert msg['show_login_phone_form_result'] == 'ok'
            log.info('Phone ok')
        elif 'show_static_password_form_result' in msg:    # Step 3.1: Static password ok
            assert msg['show_static_password_form_result'] == 'ok'
            log.info('Static password form ok: %s', msg)
        else:
            log.warn('Unknown message: %s', msg)

    def session_from_url(self, url):
        ''' Создание сессии путем GET запроса на заданный URL.
            Нужный url формируется после успешной аутентификации.
        '''
        pass

    def handshake_ok(self):
        self.opened()


class P24Client():

    def __init__(self, session:P24Session):
        self.session = session

    def get_user_info(self):
        ''' https://privat24.privatbank.ua/p24/userInfo?__=true&xref=12345678900000000000000000000000003345da&_=1466700691508 '''
        pass


class SimpleAuthFrontend:

    def query_sms_password(self):
        ''' Запрос пароля из SMS '''
        return input('SMS Password: ')

    def query_cards_pin(self, cards:dict):
        ''' Запрос пин кода карты '''
        for i in cards:
            print('{}. {}'.format(i, 1))
        card_num = input('Enter card num: ')
        card_pin = getpass.getpass('Card PIN: ')
        return (card_num, card_pin)

    def ivr_callback(self, from_num, to_num):
        print('Please make call from your number {} to number {}'.format(from_num, to_num))

def test_auth():
    from argparse import ArgumentParser
    parser = ArgumentParser(description='P24 Client library / Test program')
    parser.add_argument('-v', action='count', default=0)
    parser.add_argument('login', help='login for privat24.ua')
    args = parser.parse_args()

    log.info("P42-client test auth started")
    login = args.login
    password = getpass.getpass()

    auth = P24Authenticator()
    session = auth.authenticate(login, password)
    client = P24Client(session)

if __name__ == '__main__':
    logging.basicConfig(level = logging.DEBUG)
    test_auth()
