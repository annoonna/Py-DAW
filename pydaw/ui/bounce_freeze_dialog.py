from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)


@dataclass
class BounceFreezeOptions:
    accepted: bool = False
    include_fx: bool = True
    disable_sources: bool = False
    mute_sources: bool = False
    label: str = "Bounce"


def ask_bounce_freeze_options(
    parent,
    *,
    title: str,
    info_text: str,
    default_label: str,
    include_fx: bool = True,
    disable_sources: bool = False,
    mute_sources: bool = False,
    allow_disable_sources: bool = False,
    allow_mute_sources: bool = False,
) -> BounceFreezeOptions:
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setModal(True)
    root = QVBoxLayout(dlg)
    root.setContentsMargins(12, 12, 12, 12)
    root.setSpacing(8)

    lbl = QLabel(info_text)
    lbl.setWordWrap(True)
    root.addWidget(lbl)

    form = QFormLayout()
    ed_label = QLineEdit(str(default_label or "Bounce"))
    form.addRow("Name/Label", ed_label)
    root.addLayout(form)

    cb_fx = QCheckBox("Effekte einbeziehen (+FX)")
    cb_fx.setChecked(bool(include_fx))
    root.addWidget(cb_fx)

    cb_disable = None
    if allow_disable_sources:
        cb_disable = QCheckBox("Quellspur(en) nach dem Bounce deaktivieren/stummschalten")
        cb_disable.setChecked(bool(disable_sources))
        root.addWidget(cb_disable)

    cb_mute = None
    if allow_mute_sources:
        cb_mute = QCheckBox("Quell-Clips nach dem Bounce stummschalten")
        cb_mute.setChecked(bool(mute_sources))
        root.addWidget(cb_mute)

    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    row = QHBoxLayout()
    row.addStretch(1)
    row.addWidget(buttons)
    root.addLayout(row)

    res = BounceFreezeOptions()
    if dlg.exec() != int(QDialog.DialogCode.Accepted):
        return res
    res.accepted = True
    res.include_fx = bool(cb_fx.isChecked())
    res.disable_sources = bool(cb_disable.isChecked()) if cb_disable is not None else bool(disable_sources)
    res.mute_sources = bool(cb_mute.isChecked()) if cb_mute is not None else bool(mute_sources)
    txt = str(ed_label.text() or "").strip()
    res.label = txt or str(default_label or "Bounce")
    return res
