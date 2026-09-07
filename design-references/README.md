# Design references

The originals the shipped assets were derived from. Nothing here is served —
`frontend/public/` holds what the app actually loads.

| File | Used for |
|---|---|
| `maec-one-login.png` | the reference design `Login.jsx` implements |
| `maec-logo-original.png` | dark-ground brand logo (navy field, white "MA", gold "EC") |
| `hapext-home-original.png` | source of `public/hapext-home.jpg` |
| `rebadging-hero-original.png` | source of `public/rebadging-home.jpg` |
| `login-background-original.png` | source of `public/login-background.jpg` |

`public/maec-logo.png` is derived from the original: the navy ground is made
transparent and the white letterforms recoloured to navy, giving the
light-background lockup the reference uses. `public/maec-logo-dark.png` keeps
the original for use on dark surfaces.

`public/airsizer-home.png` is the supplied artwork, resampled to 1200 px and
reduced to a 256-colour palette (2.17 MB -> 186 KB). Its alpha channel is kept,
so the drawing sits directly on the page canvas rather than in a box.
