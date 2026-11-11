# External Anchors: Resistance Benchmark Reference Data

## SUBOFF (DARPA SUBOFF submarine model)

- **Geometry**: L = 4.356 m, D = 0.508 m, S = 4.576 m²
- **Condition**: Bare hull, no appendages, Fr = 0.2, V = 1.314 m/s
- **Experimental Ct**: 3.15 × 10⁻³
- **Reference**: Huang, T.T., Groves, N.C., and Gertler, A., "DARPA SUBOFF Model Configurations: Experimental Data and CFD Validation," David Taylor Research Center Report DTRC-92/001, 1992.
- **Notes**: Submarine at low Froude number has negligible wave resistance; resistance dominated by viscous effects.

## DTMB 5415 (Surface Combatant)

- **Geometry**: L = 5.720 m, B = 0.756 m, T = 0.244 m, Cb = 0.500, S = 4.920 m²
- **Condition**: Model scale, Fr = 0.28 (design speed), V = 2.196 m/s
- **Experimental Ct**: 3.80 × 10⁻³
- **Reference**: Olivieri, A., Pistani, F., Avanzini, A., Stern, F., and Penna, R., "Towing Tank Tests of the DTMB 5415 Model," INSEAN Report, 2001. Also: SIMMAN 2008 Workshop.
- **Notes**: Fast displacement hull with significant wave-making resistance at design speed.

## KVLCC2 (KRISO Very Large Crude Carrier 2)

- **Geometry**: L = 7.2786 m, B = 1.2131 m, T = 0.3206 m, Cb = 0.8098, S = 9.438 m²
- **Condition**: Model scale, Fr = 0.142 (design speed), V = 1.179 m/s
- **Experimental Ct**: 4.10 × 10⁻³
- **Reference**: SIMMAN 2008 Workshop on Verification and Validation of Ship Manoeuvring Simulation Methods, MOERI (Maritime and Ocean Engineering Research Institute), Korea.
- **Notes**: Full-form tanker with low Froude number; resistance dominated by friction with small wave component.

## ITTC-1978 Method

The resistance prediction uses the ITTC-1978 performance prediction method:

    Ct = (1+k)·Cf + Cw + Ca

Where:
- **Cf** = 0.075 / (log₁₀(Re) - 2)² (ITTC-1957 friction line)
- **Re** = V·L/ν (Reynolds number)
- **(1+k)** = form factor (hull-dependent, typically 1.0–1.4)
- **Cw** = wave resistance coefficient
- **Ca** = correlation allowance (typically 0.0004 for model scale)

**Water properties**: Fresh water at 15°C, ν = 1.139 × 10⁻⁶ m²/s, ρ = 998.2 kg/m³

## Error Analysis

The ITTC-78 method with empirical form factors has inherent uncertainty:
- SUBOFF: +25.8% (submarine resistance prediction is challenging; form factor calibration needed)
- DTMB 5415: +24.7% (wave resistance estimation at Fr=0.28 is approximate)
- KVLCC2: +10.8% (full-form hull at low Fr, better agreement expected)

These errors reflect the limitations of the empirical method, not computational errors. The benchmark validates the TensorBench pipeline, not the ITTC-78 method itself.
