import unittest

from src.security import authenticate, check_password, create_access_token, decode_access_token, hash_password

class TestSecurity(unittest.TestCase):
    def test_hash_and_check(self):
        pwd = "test123"
        hashed = hash_password(pwd)
        self.assertTrue(check_password(pwd, hashed))

    def test_authenticate(self):
        token = authenticate("user", "password")
        self.assertIsNotNone(token)

    def test_token_roundtrip(self):
        token = create_access_token("tester", {"roles": ["viewer"]})
        payload = decode_access_token(token)
        self.assertEqual(payload["sub"], "tester")
        self.assertEqual(payload["roles"], ["viewer"])
