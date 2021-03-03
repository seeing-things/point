from setuptools import setup, find_packages
# To use a consistent encoding
from codecs import open
from os import path

here = path.abspath(path.dirname(__file__))

# Get the long description from the README file
with open(path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='point',

    # Versions should comply with PEP440.  For a discussion on single-sourcing
    # the version across setup.py and the project code, see
    # https://packaging.python.org/en/latest/single_source_version.html
    version='0.4.1',

    description='Serial command interfaces for telescopes',
    long_description=long_description,

    url='https://github.com/bgottula/point',

    author='Brett Gottula',
    author_email='bgottula@gmail.com',

    license='MIT',

    # See https://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Topic :: Scientific/Engineering :: Astronomy',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.6',
    ],

    keywords='astronomy telescopes celestron nexstar losmandy gemini',

    packages=find_packages(exclude=['contrib', 'docs', 'tests']),

    python_requires='>=3.6',

    install_requires=[
        'pyserial>=3.0,<=3.4',  # 3.5 made compatibility-breaking changes to read_until()
    ],
)
