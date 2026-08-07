# Status — ha-bailconnect
> MàJ : 2026-08-07

**État :** intégration HACS fonctionnelle (v0.1.3) — climate, sensor, select, switch sur
le coordinator BaillConnect. Passe la 2026.8 de HA sans casse : le `config_entry` du
`DataUpdateCoordinator` est désormais explicite (obligatoire en core, jamais imposé aux
intégrations custom — vérifié dans le source du tag 2026.8.0).

**Prochaines étapes :**
- [ ] CI hassfest + HACS Action (`ignore: brands`) — absentes du repo
- [ ] `LICENSE` Apache-2.0 — la HACS Action échoue sans licence
- [ ] Release GitHub `v0.1.3` (geste de Monsieur)
