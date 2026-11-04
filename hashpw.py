import getpass, secrets
from werkzeug.security import generate_password_hash as g
p = getpass.getpass("New CRM admin password: ")
open(".env", "a").write("\nADMIN_PASSWORD_HASH=" + g(p) + "\nSECRET_KEY=" + secrets.token_hex(32) + "\n")
print("Saved.")
