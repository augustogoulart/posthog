import { useActions, useValues } from 'kea'
import React from 'react'
import imgEmptyLineGraph from 'public/empty-line-graph.svg'
import imgEmptyLineGraphDark from 'public/empty-line-graph-dark.svg'
import { QuestionCircleOutlined, LoadingOutlined, PlusCircleOutlined } from '@ant-design/icons'
import { IllustrationDanger } from 'lib/components/icons'
import { preflightLogic } from 'scenes/PreflightCheck/logic'
import { funnelLogic } from 'scenes/funnels/funnelLogic'
import { entityFilterLogic } from 'scenes/insights/ActionFilter/entityFilterLogic'
import { Button } from 'antd'

export function LineGraphEmptyState({ color, isDashboard }: { color: string; isDashboard?: boolean }): JSX.Element {
    return (
        <>
            {isDashboard ? (
                <div className="text-center" style={{ height: '100%' }}>
                    <img
                        src={color === 'white' ? imgEmptyLineGraphDark : imgEmptyLineGraph}
                        alt=""
                        style={{ maxHeight: '100%', maxWidth: '80%', opacity: 0.5 }}
                    />
                    <div style={{ textAlign: 'center', fontWeight: 'bold', marginTop: 16 }}>
                        Seems like there's no data to show this graph yet{' '}
                        <a
                            target="_blank"
                            href="https://posthog.com/docs/features/trends?utm_campaign=dashboard-empty-state&utm_medium=in-product"
                            style={{ color: color === 'white' ? 'rgba(0, 0, 0, 0.85)' : 'white' }}
                        >
                            <QuestionCircleOutlined />
                        </a>
                    </div>
                </div>
            ) : (
                <p style={{ textAlign: 'center', paddingTop: '4rem' }}>
                    We couldn't find any matching events. Try changing dates or pick another action or event.
                </p>
            )}
        </>
    )
}

export function TimeOut({ isLoading }: { isLoading: boolean }): JSX.Element {
    const { preflight } = useValues(preflightLogic)
    return (
        <div className="insight-empty-state timeout-message">
            <div className="insight-empty-state__wrapper">
                <div className="illustration-main">{isLoading ? <LoadingOutlined spin /> : <IllustrationDanger />}</div>
                <h2>{isLoading ? 'Looks like things are a little slow…' : 'Your query took too long to complete'}</h2>
                {isLoading ? (
                    <>
                        Your query is taking a long time to complete. <b>We're still working on it.</b> However, here
                        are some things you can try to speed it up:
                    </>
                ) : (
                    <>
                        Here are some things you can try to speed up your query and <b>try again</b>:
                    </>
                )}
                <ol>
                    <li>Reduce the date range of your query.</li>
                    <li>Remove some filters.</li>
                    {!preflight?.cloud && <li>Increase the size of your database server.</li>}
                    {!preflight?.cloud && !preflight?.is_clickhouse_enabled && (
                        <li>
                            <a
                                data-attr="insight-timeout-upgrade-to-clickhouse"
                                href="https://posthog.com/pricing?o=enterprise&utm_medium=in-product&utm_campaign=insight-timeout-empty-state"
                                rel="noopener"
                                target="_blank"
                            >
                                Upgrade PostHog to Enterprise Edition
                            </a>{' '}
                            and get access to a backend engineered for scale using the ClickHouse database.
                        </li>
                    )}
                    <li>
                        <a
                            data-attr="insight-timeout-raise-issue"
                            href="https://github.com/PostHog/posthog/issues/new?labels=performance&template=performance_issue_report.md"
                            target="_blank"
                            rel="noreferrer noopener"
                        >
                            Raise an issue
                        </a>{' '}
                        in our GitHub repository.
                    </li>
                    <li>
                        Get in touch with us{' '}
                        <a
                            data-attr="insight-timeout-slack"
                            href="https://posthog.com/slack"
                            rel="noopener noreferrer"
                            target="_blank"
                        >
                            on Slack
                        </a>
                        .
                    </li>
                    <li>
                        Email us at{' '}
                        <a data-attr="insight-timeout-email" href="mailto:hey@posthog.com">
                            hey@posthog.com
                        </a>
                        .
                    </li>
                </ol>
            </div>
        </div>
    )
}

export function ErrorMessage(): JSX.Element {
    return (
        <div className="insight-empty-state error-message">
            <div className="insight-empty-state__wrapper">
                <div className="illustration-main">
                    <IllustrationDanger />
                </div>
                <h2>There was an error completing this query</h2>
                <div className="mt">
                    We apologize for this unexpected situation. There are a few things you can do:
                    <ol>
                        <li>
                            First and foremost you can <b>try again</b>. We recommended you wait a few moments before
                            doing so.
                        </li>
                        <li>
                            <a
                                data-attr="insight-error-raise-issue"
                                href="https://github.com/PostHog/posthog/issues/new?labels=bug&template=bug_report.md"
                                target="_blank"
                                rel="noreferrer noopener"
                            >
                                Raise an issue
                            </a>{' '}
                            in our GitHub repository.
                        </li>
                        <li>
                            Get in touch with us{' '}
                            <a
                                data-attr="insight-error-slack"
                                href="https://posthog.com/slack"
                                rel="noopener noreferrer"
                                target="_blank"
                            >
                                on Slack
                            </a>
                            .
                        </li>
                        <li>
                            Email us at{' '}
                            <a
                                data-attr="insight-error-email"
                                href="mailto:hey@posthog.com?subject=Insight%20graph%20error"
                            >
                                hey@posthog.com
                            </a>
                            .
                        </li>
                    </ol>
                </div>
            </div>
        </div>
    )
}

export function FunnelEmptyState(): JSX.Element {
    const { filters } = useValues(funnelLogic)
    const { setFilters } = useActions(funnelLogic)
    const { addFilter } = useActions(entityFilterLogic({ setFilters, filters, typeKey: 'EditFunnel-action' }))

    return (
        <div className="insight-empty-state funnels-empty-state info-message">
            <div className="insight-empty-state__wrapper">
                <div className="illustration-main">
                    <PlusCircleOutlined />
                </div>
                <h2 className="funnels-empty-state__title">Add another step!</h2>
                <p className="funnels-empty-state__description">
                    You’re almost there! Funnels require at least two steps before calculating. Once you have two steps
                    defined, additional steps will automatically recalculate and update the funnel.
                </p>
                <Button
                    size="large"
                    onClick={() => addFilter()}
                    data-attr="add-action-event-button-empty-state"
                    icon={<PlusCircleOutlined />}
                    className="add-action-event-button"
                >
                    Add funnel step
                </Button>
                <div className="funnels-empty-state__help">
                    <a
                        data-attr="insight-funnels-emptystate-help"
                        href="https://posthog.com/docs/user-guides/funnels"
                        target="_blank"
                        rel="noreferrer noopener"
                    >
                        Learn more about funnels in our support documentation.
                    </a>
                </div>
            </div>
        </div>
    )
}
