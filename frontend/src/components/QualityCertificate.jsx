import { BadgeCheck, FileCheck2 } from 'lucide-react';
import { formatDate } from '../utils/formatters';

/**
 * Manufacturer quality certificate, laid out as an EN 10204 type 3.1
 * inspection certificate. The data comes from the passport API
 * (``quality_certificate``); its notice says when it is a sample.
 */
export default function QualityCertificateCard({ certificate }) {
  if (!certificate) return null;
  const { product } = certificate;

  const header = [
    ['Certificate no.', certificate.certificate_no, true],
    ['Date of issue', formatDate(certificate.date_of_issue)],
    ['Issued by', certificate.issued_by],
    ['Issued for', certificate.issued_for],
  ];
  const productRows = [
    ['Product', product.component_type],
    ['Component ID', product.component_id, true],
    ['Serial no.', product.serial_number, true],
    ['Material', product.material],
    ['Grade', product.grade, true],
    ['Heat / lot no.', product.heat_or_lot_no, true],
  ];

  return (
    <section className="card">
      <header className="card-header">
        <div>
          <h2 className="card-title">
            <FileCheck2 className="mr-1.5 inline h-4 w-4 text-accent" aria-hidden="true" />
            Manufacturer quality certificate
          </h2>
          <p className="mt-0.5 text-xs text-steel-500">{certificate.certificate_type}</p>
        </div>
        <span className="badge bg-emerald-100 text-emerald-800">
          <BadgeCheck className="h-3 w-3" aria-hidden="true" />
          {certificate.verdict}
        </span>
      </header>

      <div className="card-body space-y-5">
        <div className="grid gap-4 lg:grid-cols-2">
          <CertificateTable title="Certificate" rows={header} />
          <CertificateTable title="Product inspected" rows={productRows} />
        </div>

        {certificate.materials?.length ? (
          <div>
            <p className="label-caps mb-2">Material certification by part</p>
            <div className="overflow-x-auto rounded-lg border border-steel-200">
              <table className="min-w-full text-left text-xs">
                <thead className="bg-steel-50 text-[0.65rem] uppercase tracking-wide text-steel-500">
                  <tr>
                    <th className="px-3 py-2 font-semibold">Part</th>
                    <th className="px-3 py-2 font-semibold">Grade</th>
                    <th className="px-3 py-2 font-semibold">Standard</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-steel-100">
                  {certificate.materials.map((row) => (
                    <tr key={row.part}>
                      <td className="px-3 py-2 font-medium text-navy-900">{row.part}</td>
                      <td className="px-3 py-2 font-mono font-semibold text-navy-900">{row.grade}</td>
                      <td className="px-3 py-2 text-steel-600">{row.standard}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}

        <div>
          <p className="label-caps mb-2">Inspection and test results</p>
          <div className="overflow-x-auto rounded-lg border border-steel-200">
            <table className="min-w-full text-left text-xs">
              <thead className="bg-steel-50 text-[0.65rem] uppercase tracking-wide text-steel-500">
                <tr>
                  <th className="px-3 py-2 font-semibold">Test</th>
                  <th className="px-3 py-2 font-semibold">Method / standard</th>
                  <th className="px-3 py-2 font-semibold">Requirement</th>
                  <th className="px-3 py-2 font-semibold">Result</th>
                  <th className="px-3 py-2 font-semibold">Verdict</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-steel-100">
                {certificate.tests.map((row) => (
                  <tr key={row.test} className="align-top">
                    <td className="px-3 py-2 font-medium text-navy-900">{row.test}</td>
                    <td className="px-3 py-2 text-steel-600">{row.method}</td>
                    <td className="px-3 py-2 text-steel-600">{row.requirement}</td>
                    <td className="px-3 py-2 font-mono font-semibold text-navy-900">{row.result}</td>
                    <td className="px-3 py-2">
                      <span className="badge bg-emerald-100 text-emerald-800">{row.verdict}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="rounded-lg border border-steel-200 bg-steel-50 p-4 text-sm text-steel-700">
          {certificate.type_examination ? (
            <p className="mb-2">
              <span className="font-semibold text-navy-900">Type examination: </span>
              {certificate.type_examination}.
            </p>
          ) : null}
          <p>{certificate.conformity_statement}</p>
          <p className="mt-2 text-xs text-steel-500">{certificate.inspector}</p>
        </div>
      </div>

      <p className="border-t border-steel-100 px-5 py-3 text-[0.7rem] text-steel-500">{certificate.notice}</p>
    </section>
  );
}

function CertificateTable({ title, rows }) {
  return (
    <div>
      <p className="label-caps mb-2">{title}</p>
      <dl className="divide-y divide-steel-100 rounded-lg border border-steel-200 text-sm">
        {rows.map(([label, value, mono]) => (
          <div key={label} className="flex justify-between gap-4 px-3 py-1.5">
            <dt className="text-steel-500">{label}</dt>
            <dd className={mono ? 'text-right font-mono font-semibold text-navy-900' : 'text-right font-medium text-navy-900'}>
              {value || '-'}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
