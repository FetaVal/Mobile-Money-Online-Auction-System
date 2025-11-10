from django.contrib.auth.hashers import PBKDF2PasswordHasher

class PBKDF2PasswordHasher600k(PBKDF2PasswordHasher):
    """
    PBKDF2 hasher with 600,000 iterations (NIST recommended minimum)
    
    NIST SP 800-63B recommends minimum 10,000 iterations for PBKDF2-SHA256.
    OWASP recommends 600,000 iterations for PBKDF2-HMAC-SHA256 (2023 guidelines).
    
    This custom hasher ensures all new passwords use the stronger iteration count
    while maintaining backward compatibility with existing passwords.
    """
    iterations = 600_000
