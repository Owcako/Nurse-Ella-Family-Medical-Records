# Department codes

Design baseline v1.0.0. The authoritative registry is [departments.json](departments.json); this table is a readable snapshot.

Current storage is SQLite only, schema v2. Patient-first ownership is implemented in tables; the directory/file naming rules below are retained for future reference. No parallel filesystem archive is created.

These are application-local abbreviations, not national or hospital-issued codes. The backend maps exact registered department names/aliases during persistence and preserves source wording.

- Codes are exactly eight lowercase ASCII characters: a registered English abbreviation, right-padded with `0`.
- Exact registry membership is required. AI extracts source labels and evidence; the backend resolves codes.
- Unknown/unmapped/ambiguous department: `unknown0`. Multiple fully resolved departments: `multi000`.
- Published codes cannot be renamed or reused. New codes and aliases require human review and a catalog version increment.
- Preserve the source department wording separately; diagnoses, symptoms, age, tests, and hospital names do not authorize department assignment.

| Code | Abbreviation | 中文科室 | English department |
| --- | --- | --- | --- |
| `im000000` | `im` | 内科 | Internal Medicine |
| `card0000` | `card` | 心内科 | Cardiology |
| `resp0000` | `resp` | 呼吸内科 | Respiratory Medicine |
| `gastro00` | `gastro` | 消化内科 | Gastroenterology |
| `neuro000` | `neuro` | 神经内科 | Neurology |
| `neph0000` | `neph` | 肾内科 | Nephrology |
| `endo0000` | `endo` | 内分泌科 | Endocrinology |
| `heme0000` | `heme` | 血液内科 | Hematology |
| `rheum000` | `rheum` | 风湿免疫科 | Rheumatology |
| `geri0000` | `geri` | 老年医学科 | Geriatric Medicine |
| `surg0000` | `surg` | 外科 | Surgery |
| `gsurg000` | `gsurg` | 普通外科 | General Surgery |
| `ortho000` | `ortho` | 骨科 | Orthopedics |
| `nsurg000` | `nsurg` | 神经外科 | Neurosurgery |
| `tsurg000` | `tsurg` | 胸外科 | Thoracic Surgery |
| `csurg000` | `csurg` | 心外科 | Cardiac Surgery |
| `uro00000` | `uro` | 泌尿外科 | Urology |
| `hbsurg00` | `hbsurg` | 肝胆外科 | Hepatobiliary Surgery |
| `breast00` | `breast` | 乳腺外科 | Breast Surgery |
| `plast000` | `plast` | 整形外科 | Plastic Surgery |
| `vasc0000` | `vasc` | 血管外科 | Vascular Surgery |
| `ped00000` | `ped` | 儿科 | Pediatrics |
| `pedim000` | `pedim` | 小儿内科 | Pediatric Internal Medicine |
| `pedresp0` | `pedresp` | 小儿呼吸科 | Pediatric Respiratory Medicine |
| `pedgi000` | `pedgi` | 小儿消化科 | Pediatric Gastroenterology |
| `pedsurg0` | `pedsurg` | 小儿外科 | Pediatric Surgery |
| `neo00000` | `neo` | 新生儿科 | Neonatology |
| `chc00000` | `chc` | 儿童保健科 | Child Health |
| `obgyn000` | `obgyn` | 妇产科 | Obstetrics and Gynecology |
| `gyn00000` | `gyn` | 妇科 | Gynecology |
| `obs00000` | `obs` | 产科 | Obstetrics |
| `repro000` | `repro` | 生殖医学科 | Reproductive Medicine |
| `ophth000` | `ophth` | 眼科 | Ophthalmology |
| `optom000` | `optom` | 眼视光科 | Optometry |
| `ent00000` | `ent` | 耳鼻咽喉科 | Otolaryngology |
| `dent0000` | `dent` | 口腔科 | Dentistry |
| `orthod00` | `orthod` | 口腔正畸科 | Orthodontics |
| `omfs0000` | `omfs` | 口腔颌面外科 | Oral and Maxillofacial Surgery |
| `derm0000` | `derm` | 皮肤科 | Dermatology |
| `psych000` | `psych` | 精神科 | Psychiatry |
| `onc00000` | `onc` | 肿瘤科 | Oncology |
| `inf00000` | `inf` | 感染科 | Infectious Diseases |
| `tcm00000` | `tcm` | 中医科 | Traditional Chinese Medicine |
| `acu00000` | `acu` | 针灸科 | Acupuncture |
| `rehab000` | `rehab` | 康复医学科 | Rehabilitation Medicine |
| `emerg000` | `emerg` | 急诊科 | Emergency Medicine |
| `icu00000` | `icu` | 重症医学科 | Critical Care Medicine |
| `anes0000` | `anes` | 麻醉科 | Anesthesiology |
| `pain0000` | `pain` | 疼痛科 | Pain Medicine |
| `gp000000` | `gp` | 全科医学科 | General Practice |
| `prev0000` | `prev` | 预防保健科 | Preventive Medicine |
| `checkup0` | `checkup` | 体检科 | Health Examination |
| `lab00000` | `lab` | 医学检验科 | Laboratory Medicine |
| `rad00000` | `rad` | 医学影像科 | Medical Imaging |
| `us000000` | `us` | 超声医学科 | Ultrasound Medicine |
| `path0000` | `path` | 病理科 | Pathology |
| `nucmed00` | `nucmed` | 核医学科 | Nuclear Medicine |
| `trans000` | `trans` | 输血科 | Transfusion Medicine |
| `pharm000` | `pharm` | 临床药学科 | Clinical Pharmacy |
| `scope000` | `scope` | 内镜科 | Endoscopy |

## Patient-first directory layout

See [record-layout.json](record-layout.json) for naming rules and the confirmed SQLite decision. The filesystem layout below is inactive future reference only.

```text
data/
  inbox/
  index-pending/<record_id>.json  # conditional filesystem-marker proposal
  records/
    zhang-san/
      patient.json
      2026-03-31-pedim000-<record_id>/
        record.json
        __abstract.json
        documents/<document_id>/
          raw.jpg
          text.initial.txt
          text.current.txt
          document.json
    _unassigned/
      <date>-<department_code>-<record_id>/
        ...
```

Patient slugs are unique user-confirmed ASCII names. `_unassigned` is a bucket of independent unresolved records, not a family profile.
Dates retain confirmed printed precision; use `date-unknown` when unresolved. Same-day visits remain distinct through record IDs.
Folder names are readable labels; patient/record/document IDs in metadata remain the identity.
New or changed data atomically invalidates the archive index through SQLite `index_jobs`. `record_abstracts` records the indexed archive revision and partial/current/stale status. No filesystem queue or marker files are used.
Existing SQLite data has not been migrated to this layout.
