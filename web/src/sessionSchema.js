function asNonEmptyText(value, fieldLabel) {
  const text = String(value || "").trim();
  if (!text) {
    throw new Error(`${fieldLabel}不能为空`);
  }
  return text;
}

function normalizeStylePreference(value) {
  const normalized = String(value || "auto").trim();
  const allowed = new Set(["auto", "darkEpic", "warmHealing", "realism", "fantasyGrand"]);
  if (!allowed.has(normalized)) {
    throw new Error("导演风格偏好不合法");
  }
  return normalized;
}

export function parseCreativeSession(candidate) {
  const payload = candidate && typeof candidate === "object" ? candidate : {};
  return {
    workTitle: asNonEmptyText(payload.workTitle, "作品名称"),
    endingDirection: asNonEmptyText(payload.endingDirection, "结局方向"),
    stylePreference: normalizeStylePreference(payload.stylePreference)
  };
}
