import re

from app.services.sha512_crypt import sha512_crypt


def test_published_vectors():
    # From "Unix crypt using SHA-256 and SHA-512" (Drepper), the reference test cases.
    assert sha512_crypt("Hello world!", "saltstring") == (
        "$6$saltstring$svn8UoSVapNtMuq1ukKS4tPQd8iKwSMHWjl/O817G3uBnIFNjnQJuesI68u4OTLiBFdcbYEdFCoEOfaS35inz1")
    assert sha512_crypt("Hello world!", "saltstringsaltstring", 10000) == (
        "$6$rounds=10000$saltstringsaltst$OW1/O6BYHV6BcXZu8QVeXbDWra3Oeqh0sbHbbMCVNSnCM/UrjmM0Dp8vOuZeHBy/YTBmSK6H9qs/y3RnOaw5v.")
    assert sha512_crypt("This is just a test", "toolongsaltstring", 5000) == (
        "$6$rounds=5000$toolongsaltstrin$lQ8jolhgVRVhY4b5pZKaysCLi0QBxGoNeKQzQ3glMhwllF7oGDZxUhx1yxdYcz/e1JSbq3y6JMxxl8audkUEm0")


def test_random_salt_shape():
    value = sha512_crypt("Fixture-Pass-1")
    assert re.fullmatch(r"\$6\$[./0-9A-Za-z]{16}\$[./0-9A-Za-z]{86}", value)
    assert value != sha512_crypt("Fixture-Pass-1")
