// DEPRECATED: We now use the PersonModal.tsx to show person information for funnels
import React from 'react'
import { useValues } from 'kea'
import { funnelLogic } from './funnelLogic'
import { Link } from 'lib/components/Link'
import { percentage, Loading } from 'lib/utils'
import { EntityTypes } from '~/types'
import './FunnelPeople.scss'
import { Card } from 'antd'

export function People(): JSX.Element | null {
    const { stepsWithCount, peopleSorted, peopleLoading } = useValues(funnelLogic({}))
    if (!stepsWithCount) {
        return null
    }

    return (
        <Card title="Per user" className="funnel-people" style={{ marginTop: 16 }}>
            {peopleLoading ? (
                <Loading style={{ minHeight: 50 }} />
            ) : !peopleSorted || peopleSorted.length === 0 ? (
                <div style={{ textAlign: 'center', margin: '3rem 0' }}>No users found for this funnel.</div>
            ) : (
                <table className="table-bordered full-width">
                    <tbody>
                        <tr>
                            <th />
                            {stepsWithCount.map((step, index) => (
                                <th key={index}>
                                    {step.type === EntityTypes.ACTIONS ? (
                                        <Link to={'/action/' + step.action_id}>{step.name}</Link>
                                    ) : (
                                        step.name
                                    )}
                                </th>
                            ))}
                        </tr>
                        <tr>
                            <td />
                            {stepsWithCount.map((step, index) => (
                                <td key={index}>
                                    {step.count}&nbsp;{' '}
                                    {step.count > 0 && (
                                        <span>({percentage(step.count / stepsWithCount[0].count)})</span>
                                    )}
                                </td>
                            ))}
                        </tr>
                        {peopleSorted.map((person) => (
                            <tr key={person.id} data-attr="funnel-person">
                                <td className="text-overflow">
                                    <Link to={`/person/${encodeURIComponent(person.distinct_ids[0])}`}>
                                        {person.name}
                                    </Link>
                                </td>
                                {stepsWithCount.map((step, index) => (
                                    <td
                                        key={index}
                                        className={
                                            (step.people?.indexOf(person.uuid) ?? -1) > -1
                                                ? 'funnel-success'
                                                : 'funnel-dropped'
                                        }
                                    />
                                ))}
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
        </Card>
    )
}
