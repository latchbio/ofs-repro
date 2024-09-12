import os
import random
import string
from pathlib import Path


def random_string(length):
    return ''.join(random.choice(string.ascii_letters) for _ in range(length))

# Define the shared directory
shared_dir = Path(f"/nf-workdir/{os.environ.get('LATCH_RUN_ID')}")
print(f"Shared directory: {shared_dir}")

# Read contents from random_data.txt in the shared directory
random_data_file = shared_dir / "random_data.txt"
with open(random_data_file, "rb") as f:
    random_data_content = f.read()
print(f"Read {len(random_data_content)} bytes from {random_data_file}")


# Write a file to the shared directory
test_file = shared_dir / "random_out.txt"
test_content = random_string(100)
with open(test_file, "w") as f:
    f.write(test_content)
print(f"Wrote content to {test_file}")

# Read the file back
with open(test_file, "r") as f:
    read_content = f.read()
print(f"Read content from {test_file}")

# Verify the content
if read_content == test_content:
    print("Content verification successful")
else:
    print("Content verification failed")

# List files in the shared directory
print("Files in shared directory:")
for file in shared_dir.iterdir():
    print(f"- {file.name}")

# Clean up
os.remove(test_file)
print(f"Removed {test_file}")

# Verify removal
if not test_file.exists():
    print("File removal successful")
else:
    print("File removal failed")

# Write exitcode of 0 to a file in the shared directory
exitcode_file = shared_dir / "exitcode.txt"
with open(exitcode_file, "w") as f:
    f.write("0")
    f.flush()
    os.fsync(f.fileno())
print(f"Wrote exitcode 0 to {exitcode_file} and fsynced to disk")

# Verify the exitcode file was created and contains the correct value
if exitcode_file.exists():
    with open(exitcode_file, "r") as f:
        exitcode_content = f.read().strip()
    if exitcode_content == "0":
        print("Exitcode file creation and content verification successful")
    else:
        print(f"Exitcode file content verification failed. Expected 0, got {exitcode_content}")
else:
    print("Exitcode file creation failed")
