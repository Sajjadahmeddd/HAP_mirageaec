# Design references

The originals the shipped assets were derived from. Nothing here is served —
`frontend/public/` holds what the app actually loads.

| File | Used for |
|---|---|
| `maec-one-login.png` | the reference design `Login.jsx` implements |
| `maec-logo-original.png` | dark-ground brand logo (navy field, white "MA", gold "EC") |
| `hapext-home-original.png` | source of `public/hapext-home.jpg` |

`public/maec-logo.png` is derived from the original: the navy ground is made
transparent and the white letterforms recoloured to navy, giving the
light-background lockup the reference uses. `public/maec-logo-dark.png` keeps
the original for use on dark surfaces.

## Missing: the AirSizer Pro hero

`AirsizerPro home page.png` arrived truncated — the copy stopped about a third
of the way in, so it has no PNG end marker and cannot be decoded. Save it again
as:

    frontend/public/airsizer-home.jpg

`airsizer/Home.jsx` already points there and falls back to the drawn `DuctArt`
until the file exists, so the page is never broken — the artwork simply appears
once the file lands.
