import asyncio
import unittest
import hashlib
from unittest.mock import MagicMock, AsyncMock, patch, ANY
from core_checker import IPTVChecker
import yarl

class TestStalkerChecker(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.checker = IPTVChecker()
        self.mac = "00:1A:79:00:00:00"

    def test_normalize_url(self):
        self.assertEqual(self.checker._normalize_stalker_url("http://test.com/c/"), "http://test.com")
        self.assertEqual(self.checker._normalize_stalker_url("http://test.com/stalker_portal/server/load.php"), "http://test.com")
        self.assertEqual(self.checker._normalize_stalker_url("http://test.com"), "http://test.com")

    def test_generate_serial(self):
        # MD5 of 00:1A:79:00:00:00 is 530402e3b20757758296715694262174
        # First 13 chars upper: 530402E3B2075
        expected = hashlib.md5(self.mac.encode()).hexdigest()[:13].upper()
        self.assertEqual(self.checker._generate_serial(self.mac), expected)

    async def test_handshake_standard_success(self):
        session = MagicMock()
        cm = AsyncMock()
        cm.__aenter__.return_value.status = 200
        cm.__aenter__.return_value.json.return_value = {'js': {'token': 'standard_token'}}
        session.get.return_value = cm

        token = await self.checker._stalker_handshake(session, "http://test.com/load.php", self.mac)
        self.assertEqual(token, 'standard_token')

    async def test_get_profile_signature_logic(self):
        session = MagicMock()
        # Mock cookie jar
        session.cookie_jar = MagicMock()

        cm = AsyncMock()
        cm.__aenter__.return_value.status = 200
        cm.__aenter__.return_value.json.return_value = {'js': {'id': '123'}}
        session.get.return_value = cm

        await self.checker._stalker_get_profile(session, "http://test.com/load.php", "token", self.mac)

        # Verify call args for signature correctness
        args, kwargs = session.get.call_args
        params = kwargs['params']

        sn = self.checker._generate_serial(self.mac)
        dev_id = hashlib.sha256(self.mac.encode()).hexdigest().upper()

        # Check signature construction: mac + sn + device_id + device_id2
        sig_source = f"{self.mac}{sn}{dev_id}{dev_id}"
        expected_sig = hashlib.sha256(sig_source.encode()).hexdigest().upper()

        self.assertEqual(params['sn'], sn)
        self.assertEqual(params['signature'], expected_sig)

    async def test_token_rotation(self):
        session = MagicMock()
        session.cookie_jar = MagicMock()

        cm = AsyncMock()
        cm.__aenter__.return_value.status = 200
        # Return new token in response
        cm.__aenter__.return_value.json.return_value = {'js': {'id': '123', 'token': 'new_rotated_token'}}
        session.get.return_value = cm

        await self.checker._stalker_get_profile(session, "http://test.com/load.php", "old_token", self.mac)

        # Check if cookie jar was updated with new token
        session.cookie_jar.update_cookies.assert_called_with({'token': 'new_rotated_token'}, response_url=ANY)

if __name__ == '__main__':
    unittest.main()
