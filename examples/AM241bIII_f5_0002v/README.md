# AM 241 b III fol. 5, 0002v

Development leaf (Árni Magnússon Institute scan `AM02-0241-b-III_0002v.hq`, 8125 × 11058 px,
300 ppi). The scan itself is not included; place it here as
`AM241bIII_f5_0002v.pdf` (any file name works if you pass it explicitly).

- `AM241bIII_f5_0002v.corrections.json`: the corrections made by eye after the automatic pass
  (24 clefs incl. mid-staff changes, 3 flats, 118 dropped false heads, 2 added heads,
  2 forced groups, 12 flags).
- `config.json`: fixes the working scale at 0.5, the scale the corrections were made at,
  so the replay matches the hand-checked labels as closely as possible.

```bash
chantlabel run AM241bIII_f5_0002v.pdf -o out/ --title "AM 241 b III fol. 5, 0002v" \
    --config config.json --corrections AM241bIII_f5_0002v.corrections.json
```

Replaying the corrections reproduces the hand-checked labels at head F1 0.994,
pitch accuracy 0.998 and grouping F1 1.0. The few differences are heads within a
pixel or two of a band or rounding boundary.
