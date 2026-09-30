import hashlib
import binascii
import hmac

def hash_pw(pw: str, salt: bytes) -> str:
    key = hashlib.pbkdf2_hmac('sha256', pw.encode('utf-8'), salt, 100_000)
    return f"pbkdf2_sha256:100000:{binascii.hexlify(salt).decode()}:{binascii.hexlify(key).decode()}"

def verify_pw(pw: str, stored_hash: str) -> bool:
    try:
        parts = stored_hash.split(':')
        if len(parts) != 4 or parts[0] != 'pbkdf2_sha256':
            return False
        iterations = int(parts[1])
        salt = binascii.unhexlify(parts[2])
        expected_key = binascii.unhexlify(parts[3])
        key = hashlib.pbkdf2_hmac('sha256', pw.encode('utf-8'), salt, iterations)
        return hmac.compare_digest(key, expected_key)
    except Exception:
        return False

salt_admin = b'lcm_chopo_adm_26'
salt_user = b'lcm_chopo_usr_26'

admin_pw = '6bswEsFXREyVJwR'
user_pw = 'qUF6h5SNcfS4zjs'

h_admin = hash_pw(admin_pw, salt_admin)
h_user = hash_pw(user_pw, salt_user)

print("ADMIN_HASH =", repr(h_admin))
print("USER_HASH  =", repr(h_user))
print("Verify admin right:", verify_pw(admin_pw, h_admin))
print("Verify admin wrong:", verify_pw('wrong', h_admin))
print("Verify user right :", verify_pw(user_pw, h_user))
print("Verify user wrong :", verify_pw('wrong', h_user))
