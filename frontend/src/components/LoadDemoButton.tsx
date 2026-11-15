import { useLoadDemo } from '../lib/queries';
import { errorDetail, useToast } from './Toast';
import { Button } from './Ui';

export default function LoadDemoButton({ compact = false }: { compact?: boolean }) {
  const load = useLoadDemo();
  const { notify } = useToast();
  const onLoad = async () => {
    try {
      await load.mutateAsync();
      notify('Demo data is ready for review.');
    } catch (reason) {
      notify(errorDetail(reason), 'error');
    }
  };
  return (
    <Button type="button" onClick={onLoad} disabled={load.isPending}>
      {load.isPending ? 'Loading demo data…' : compact ? 'Load demo data' : 'Load demo data'}
    </Button>
  );
}
