"use client";

import { useState } from "react";
import { LeadSchema, type HandoffRequest, type Lead } from "@/lib/protocol";
import type { Dictionary } from "@/lib/i18n";

/**
 * Formulario de handoff (README §13).
 *
 * Estado terminal del grafo. Dos decisiones que no son estéticas:
 *
 *  - El consentimiento se envía junto a la VERSIÓN del texto aceptado. El
 *    consentimiento se audita por versión, no por contenido: si mañana cambia
 *    la redacción, hay que poder saber qué aceptó exactamente este usuario.
 *  - Se listan los datos que FALTAN, en lenguaje llano. Ocultarlos daría la
 *    impresión de que la selección está cerrada, y no lo está.
 */

interface HandoffFormProps {
  request: HandoffRequest;
  dict: Dictionary;
  disabled: boolean;
  onSubmit: (lead: Lead) => void;
}

interface FieldErrors {
  name?: string;
  email?: string;
  consent?: string;
}

export function HandoffForm({
  request,
  dict,
  disabled,
  onSubmit,
}: HandoffFormProps) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [company, setCompany] = useState("");
  const [country, setCountry] = useState("");
  const [consent, setConsent] = useState(false);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [submitted, setSubmitted] = useState(false);

  function handleSubmit(): void {
    const next: FieldErrors = {};
    if (!name.trim()) next.name = dict.handoff.required;
    if (!consent) next.consent = dict.handoff.required;

    const candidate = {
      name: name.trim(),
      email: email.trim(),
      company: company.trim() || null,
      country: country.trim() || null,
      consentAccepted: consent,
      consentTextVersion: request.consentTextVersion,
    };

    const parsed = LeadSchema.safeParse(candidate);

    if (!parsed.success) {
      // El único campo con formato propio es el email; el resto se cubre arriba.
      if (email.trim() && !next.email) next.email = dict.handoff.invalidEmail;
      if (!email.trim()) next.email = dict.handoff.required;
    }

    if (Object.keys(next).length > 0 || !parsed.success) {
      setErrors(next);
      return;
    }

    setErrors({});
    setSubmitted(true);
    onSubmit(parsed.data);
  }

  if (submitted) {
    return (
      <div
        role="status"
        className="shrink-0 rounded-lg border border-accent bg-surface-raised p-3 text-sm"
      >
        {dict.handoff.done}
      </div>
    );
  }

  return (
    <section className="shrink-0 rounded-lg border border-accent bg-surface-raised p-3">
      <h2 className="text-sm font-semibold">{dict.handoff.title}</h2>
      <p className="mt-1 text-xs text-fg-muted">
        {dict.handoff.reason[request.reason]}
      </p>
      <p className="mt-2 text-sm leading-relaxed">{dict.handoff.body}</p>

      {request.summaryForUser && (
        <blockquote className="mt-2 border-l-2 border-border-subtle pl-2 text-xs leading-relaxed text-fg-muted">
          {request.summaryForUser}
        </blockquote>
      )}

      {request.missing.length > 0 && (
        <div className="mt-3">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-fg-muted">
            {dict.handoff.missingIntro}
          </p>
          <ul className="mt-1 flex flex-wrap gap-1.5">
            {request.missing.map((slot) => (
              <li
                key={slot}
                className="rounded-full border border-warn-border bg-warn-surface px-2 py-0.5 text-[11px] text-warn-fg"
              >
                {dict.slots[slot]}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <Field
          id="lead-name"
          label={dict.handoff.name}
          value={name}
          onChange={setName}
          error={errors.name}
          required
          autoComplete="name"
        />
        <Field
          id="lead-email"
          label={dict.handoff.email}
          value={email}
          onChange={setEmail}
          error={errors.email}
          required
          type="email"
          autoComplete="email"
        />
        <Field
          id="lead-company"
          label={dict.handoff.company}
          value={company}
          onChange={setCompany}
          autoComplete="organization"
        />
        <Field
          id="lead-country"
          label={dict.handoff.country}
          value={country}
          onChange={setCountry}
          autoComplete="country-name"
        />
      </div>

      <div className="mt-3">
        <label className="flex items-start gap-2 text-xs leading-relaxed">
          <input
            type="checkbox"
            checked={consent}
            onChange={(event) => setConsent(event.target.checked)}
            aria-invalid={errors.consent ? true : undefined}
            className="mt-0.5 size-4 shrink-0 accent-[var(--accent)]"
          />
          <span>{dict.handoff.consentText}</span>
        </label>
        {errors.consent && (
          <p className="mt-1 text-[11px] text-warn-fg">{errors.consent}</p>
        )}
        {/* Trazabilidad del consentimiento: versión visible, no solo enviada. */}
        <p className="mt-1 font-mono text-[10px] text-fg-muted">
          {request.consentTextVersion}
        </p>
      </div>

      <button
        type="button"
        onClick={handleSubmit}
        disabled={disabled}
        className="mt-3 w-full rounded-md bg-accent px-3 py-2 text-sm font-medium text-accent-contrast enabled:hover:bg-accent-hover disabled:opacity-40 sm:w-auto"
      >
        {disabled ? dict.handoff.submitting : dict.handoff.submit}
      </button>
    </section>
  );
}

function Field({
  id,
  label,
  value,
  onChange,
  error,
  required = false,
  type = "text",
  autoComplete,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  error?: string;
  required?: boolean;
  type?: string;
  autoComplete?: string;
}) {
  return (
    <div>
      <label htmlFor={id} className="block text-[11px] font-medium text-fg-muted">
        {label}
        {required && <span aria-hidden="true"> *</span>}
      </label>
      <input
        id={id}
        type={type}
        value={value}
        required={required}
        autoComplete={autoComplete}
        onChange={(event) => onChange(event.target.value)}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-error` : undefined}
        className={[
          "mt-0.5 w-full rounded-md border bg-surface px-2 py-1.5 text-sm outline-none focus:border-accent",
          error ? "border-warn-border" : "border-border-subtle",
        ].join(" ")}
      />
      {error && (
        <p id={`${id}-error`} className="mt-0.5 text-[11px] text-warn-fg">
          {error}
        </p>
      )}
    </div>
  );
}
