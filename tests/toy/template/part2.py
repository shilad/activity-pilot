"""Part 2: how many prime numbers are smaller than 100."""


def is_prime(n):
    return n > 1 and all(n % d for d in range(2, int(n ** 0.5) + 1))


print(sum(1 for n in range(100) if is_prime(n)))
