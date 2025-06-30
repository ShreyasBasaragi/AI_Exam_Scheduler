import subprocess
import sys

# List of required packages
REQUIRED_PACKAGES = [
    'Flask',                  # Web framework
    'mysql-connector-python', # MySQL driver
    'pandas',                 # Data manipulation
    'XlsxWriter'              # Excel writer engine for pandas
]


def install_packages(packages):
    """
    Installs the given list of packages using pip.
    """
    try:
        subprocess.check_call([
            sys.executable, '-m', 'pip', 'install', *packages
        ])
        print("All packages installed successfully.")
    except subprocess.CalledProcessError as err:
        print(f"Error during installation: {err}")
        sys.exit(1)


if __name__ == '__main__':
    install_packages(REQUIRED_PACKAGES)
