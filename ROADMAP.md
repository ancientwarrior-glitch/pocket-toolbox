# Pocket Toolbox roadmap

Current work is password protection before new visual features.

1. **Interface password sessions (0.2.4 beta):** create a separate toolbox password, require it on reopening, lock on exit/inactivity, and close related local boards. This does not encrypt working files.
2. **Working-record encryption:** protect notes, journal and financial data at rest with a reviewed recovery/migration design. This is unfinished; do not treat the current interface lock as an encrypted vault.
3. **Widgets:** add a direct Finance shortcut while keeping all shortcuts behind the same password flow.
4. **Visual tools:** dedicated functional views for journal, notes, RSS and the remaining tools, integrated with existing Finance/project/main boards and shared records.
5. **App packaging:** use the tested flows and common records to shape an Android app; pursue free/open-source distribution including F-Droid, with no advertising or telemetry. Packaging and distribution are future work.

Implement one stage at a time, preserve existing records, test upgrades and restore paths, and document the limits of every security feature.
