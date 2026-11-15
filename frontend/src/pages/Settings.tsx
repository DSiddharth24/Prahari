import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import PageHeader from '../components/PageHeader';
import { errorDetail, useErrorToast, useToast } from '../components/Toast';
import { Button, ErrorState, FormField, LoadingSkeleton, controlClass } from '../components/Ui';
import { usePutSettings, useSettings } from '../lib/queries';
import type { Settings } from '../lib/types';

export default function SettingsPage() {
  const query = useSettings();
  const save = usePutSettings();
  useErrorToast(query.error);
  const { notify } = useToast();
  const [values, setValues] = useState<Settings | null>(null);
  const [rulesYaml, setRulesYaml] = useState('');
  const [assetsText, setAssetsText] = useState('');

  useEffect(() => {
    if (!query.data) return;
    setValues(query.data.settings);
    setRulesYaml(query.data.rules_yaml);
    setAssetsText(query.data.settings.critical_assets.join('\n'));
  }, [query.data]);

  const setNumber = (key: 'correlation_window_hours' | 'dedupe_window_minutes' | 'minutes_saved_per_alert', value: string) => {
    setValues((current) => current ? { ...current, [key]: Number(value) } : current);
  };
  const saveSettings = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!values) return;
    try {
      await save.mutateAsync({
        settings: { ...values, critical_assets: assetsText.split(/\r?\n/).map((asset) => asset.trim()).filter(Boolean) },
        rules_yaml: rulesYaml,
      });
      notify('Settings saved.');
    } catch (reason) {
      notify(errorDetail(reason), 'error');
    }
  };

  return (
    <>
      <PageHeader title="Settings" description="Tune how alerts are grouped and name systems that need closer review." />
      {query.isLoading ? <LoadingSkeleton rows={5} /> : null}
      {query.isError ? <ErrorState message={errorDetail(query.error)} onRetry={() => void query.refetch()} /> : null}
      {values ? (
        <form className="max-w-4xl space-y-8" onSubmit={saveSettings}>
          <section aria-labelledby="rules-heading">
            <h2 id="rules-heading" className="mb-1 text-16 font-semibold">Suppression rules</h2>
            <p className="mb-3 text-13 text-text-secondary">Edit the rule text that identifies routine or duplicate alerts. Invalid YAML is rejected by the server.</p>
            <FormField label="Rules YAML">
              <textarea
                className={controlClass('min-h-64 resize-y font-mono text-13 leading-relaxed')}
                value={rulesYaml}
                onChange={(event) => setRulesYaml(event.target.value)}
                spellCheck={false}
                autoCapitalize="off"
                autoCorrect="off"
              />
            </FormField>
          </section>
          <section aria-labelledby="windows-heading">
            <h2 id="windows-heading" className="mb-3 text-16 font-semibold">Alert windows</h2>
            <div className="grid gap-4 sm:grid-cols-3">
              <FormField label="Correlation window (hours)" hint="Alerts in this time range can be linked.">
                <input type="number" min="1" max="168" step="1" className={controlClass()} value={values.correlation_window_hours} onChange={(event) => setNumber('correlation_window_hours', event.target.value)} required />
              </FormField>
              <FormField label="Deduplication window (minutes)" hint="Repeated alerts within this period can be merged.">
                <input type="number" min="1" max="1440" step="1" className={controlClass()} value={values.dedupe_window_minutes} onChange={(event) => setNumber('dedupe_window_minutes', event.target.value)} required />
              </FormField>
              <FormField label="Minutes saved per alert (estimate)" hint="Used only for the dashboard estimate.">
                <input type="number" min="0" max="1440" step="1" className={controlClass()} value={values.minutes_saved_per_alert} onChange={(event) => setNumber('minutes_saved_per_alert', event.target.value)} required />
              </FormField>
            </div>
          </section>
          <section aria-labelledby="assets-heading">
            <h2 id="assets-heading" className="mb-1 text-16 font-semibold">Critical assets</h2>
            <p className="mb-3 text-13 text-text-secondary">One asset name per line. These names help analysts identify systems that need prompt review.</p>
            <FormField label="Asset names">
              <textarea className={controlClass('min-h-28 resize-y')} value={assetsText} onChange={(event) => setAssetsText(event.target.value)} />
            </FormField>
          </section>
          {save.isError ? <p role="alert" className="border-l-4 border-error bg-surface px-3 py-2 text-13 text-error">{errorDetail(save.error)}</p> : null}
          <div className="border-t border-border pt-4">
            <Button type="submit" disabled={save.isPending}>
              {save.isPending ? 'Saving settings…' : 'Save settings'}
            </Button>
          </div>
        </form>
      ) : null}
    </>
  );
}
