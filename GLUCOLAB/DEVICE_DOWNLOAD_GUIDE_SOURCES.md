# GLUCOLAB — device-specific Show Method instructions

The **Show Method** link in each upload card now opens a matching help page for the selected device. All guides load through the existing local GLUCOLAB homepage (for example, `/?guide=sensor-dexcomg7`). This update changes the **frontend instructions only**. It does not expand the Python CSV parser or imply that every manufacturer's export is automatically compatible.

| Device(s) | Verified download / reporting method | Notes |
|---|---|---|
| Libre 2, Libre 2 Plus, Libre 3, Libre 3 Plus | [Abbott LibreView, Glucose History → Download Glucose Data](https://www.freestyle.abbott/en-us/support/faq/apps/downloading-glucose-data-from-the-freestyle-libre-3-app.html) | Raw glucose export, not report PDFs |
| Dexcom G6, G7 | [Dexcom Clarity → Reports → CSV Export](https://www.dexcom.com/en-us/faqs/can-i-export-raw-data) | Export may vary by region and version |
| Guardian 4, Simplera / Simplera Sync | [Medtronic CareLink](https://www.medtronic-diabetes.com/en-IE/help-center/faqs/how-do-i-upload-my-device-data-carelink-personal) | Standalone Simplera and pump-paired Simplera Sync follow different sync paths; raw CSV needs validation |
| Eversense 365 | [Eversense 365 app → Menu → Reports → PDF sharing](https://www.eversensecgm.com/faq/?page=4) | No verified raw glucose CSV workflow; summary PDFs do not replace timestamped records |
| MiniMed 600 Series, 700 Series | [Medtronic CareLink](https://origin.medtronicdiabetes.com/customer-support/carelink-software-support/using-carelink-software) | Device upload method varies; current CSV export availability depends on account/region |
| Omnipod 5 | [Omnipod 5 → Glooko](https://www.omnipod.com/en-gb/current-podders/resources/omnipod-5/faqs/data-management), then [Glooko → Export to CSV](https://support.glooko.com/hc/en-gb/articles/4460340377875-How-can-I-export-my-diabetes-data-from-Glooko) | Glooko downloads a ZIP; extract CSVs before upload |
| Tandem t:slim X2 and Tandem Mobi | [Tandem Source user guide: Daily Timeline → Export CSV](https://www.tandemdiabetes.com/docs/default-source/user-guide/user-guide-tandem-source-personal-mmoll-intl-aw1013216.pdf?sfvrsn=73553bd7_163) | File must contain recognizable timestamped basal-rate events; Mobi synchronizes through its mobile app |
| iLet Bionic Pancreas | [Beta Bionics user resources](https://www.betabionics.com/user-resources/) | A raw basal-event CSV export was not verified |
| mylife YpsoPump | [Ypsomed mylife Software, Logbook CSV/Excel](https://www.mylife-diabetescare.com/en/products/therapy-management/faq-software) | [mylife Cloud/software transition](https://www.mylife-diabetescare.com/en/products/therapy-management/mylife-digital/mylife-cloud-phase-out); export availability may differ by region |

All references were checked on 2026-11-22. Product interfaces may change. For private use, download your own data and keep raw medical records confidential.
