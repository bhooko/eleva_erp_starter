# Eleva ERP – QC profile patch

This patch adds **Stage** and **Lift Type** choices to the QC form creation flow.

### Files
- `qc_profile.py` — Flask **Blueprint** with a small SQLite table `qc_form_profiles`.
- `templates/forms_new.html` — The New Form page including **Stage** and **Lift Type** selectors.

### How to install
1. Place `qc_profile.py` in your project root (same folder as `app.py`).  
2. Place `templates/forms_new.html` in your project's `templates/` folder.  
3. In `app.py`, register the blueprint:
   ```python
   from qc_profile import qc_bp
   app.register_blueprint(qc_bp)  # exposes /forms/new
   ```
4. Your existing “+ New form” link should go to `url_for('qc.forms_new')` or `/forms/new`.
5. The profile is stored in `instance/eleva_qc.db` (created automatically).

### Notes
- Stages: Template QC, Stage 1, Stage 2, Stage 3, Completion, Structure, Cladding, Service, Repair, Material.
- Lift types: Hydraulic, MRL, MR, Dumbwaiter, Goods.
- The base template already sets the body title (“QC – New form”) when visiting `/forms/new`.
