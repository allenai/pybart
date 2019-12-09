import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="ud2ude",
    version="2.1.0",
    author="Aryeh Tiktinsky",
    author_email="aryehgigi@gmail.com",
    description="python converter from UD to enhanced UD representations",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/allenai/UD2UDE",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
)