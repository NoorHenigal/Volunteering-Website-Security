# Argon2 profile startup check

This application supports multiple Argon2 profiles via the `.env` setting `ARGON2_PROFILE`.

## What happened?

The application stopped during startup because `ARGON2_PROFILE=RFC_9106_HIGH_MEMORY` was selected, but your machine does not meet the minimum recommended host specifications.

The RFC 9106 “high memory” profile uses **~2 GiB RAM per hash operation**. On machines with low total RAM, this can lead to failures.

## How to fix

1. Open your `.env` file.
2. Set:

    ```env
    ARGON2_PROFILE=RFC_9106_LOW_MEMORY
    ```

3. Start the app again.

The `RFC_9106_LOW_MEMORY` profile uses ~64 MiB RAM per hash and is suitable for laptops and small VMs.

## Important notes

- Existing passwords will still verify correctly because Argon2 encodes its parameters into the stored hash.
- Switching profiles changes the cost for **new** password hashes.
