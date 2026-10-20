import { NavLink, useLocation } from 'react-router-dom';
import { MoreHorizontal } from 'lucide-react';
import { NAV_ITEMS } from './Sidebar';
import { cx } from '../utils/formatters';

/** The four destinations a user accesses most; everything else is under More. */
const PRIMARY = ['/', '/components', '/prediction', '/analytics'];

/** Thumb-reachable bottom tab bar for phones and small tablets. */
export default function MobileNav({ onOpenMore }) {
  const { pathname } = useLocation();
  const items = PRIMARY.map((to) => NAV_ITEMS.find((item) => item.to === to));
  const inPrimary = items.some((item) => (item.to === '/' ? pathname === '/' : pathname.startsWith(item.to)));

  return (
    <nav
      className="no-print fixed inset-x-0 bottom-0 z-40 border-t border-steel-200 bg-white/95 backdrop-blur lg:hidden"
      style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
      aria-label="Quick navigation"
    >
      <ul className="mx-auto grid max-w-lg grid-cols-5">
        {items.map((item) => (
          <li key={item.to}>
            <NavLink
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                cx(
                  'flex h-16 flex-col items-center justify-center gap-1 text-[0.65rem] font-semibold',
                  isActive ? 'text-accent-dark' : 'text-steel-500 active:bg-steel-100',
                )
              }
            >
              {({ isActive }) => (
                <>
                  <span
                    className={cx(
                      'flex h-7 w-12 items-center justify-center rounded-full transition-colors',
                      isActive ? 'bg-accent/15' : '',
                    )}
                  >
                    <item.icon className="h-5 w-5" aria-hidden="true" />
                  </span>
                  {item.short}
                </>
              )}
            </NavLink>
          </li>
        ))}
        <li>
          <button
            type="button"
            onClick={onOpenMore}
            className={cx(
              'flex h-16 w-full flex-col items-center justify-center gap-1 text-[0.65rem] font-semibold',
              inPrimary ? 'text-steel-500 active:bg-steel-100' : 'text-accent-dark',
            )}
            aria-label="More pages"
          >
            <span
              className={cx(
                'flex h-7 w-12 items-center justify-center rounded-full',
                inPrimary ? '' : 'bg-accent/15',
              )}
            >
              <MoreHorizontal className="h-5 w-5" aria-hidden="true" />
            </span>
            More
          </button>
        </li>
      </ul>
    </nav>
  );
}
