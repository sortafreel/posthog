import clsx from 'clsx'
import { useActions, useValues } from 'kea'
import { useCallback, useEffect, useState } from 'react'

import {
    IconArrowRight,
    IconBolt,
    IconBuilding,
    IconChevronDown,
    IconChevronLeft,
    IconChevronRight,
    IconClock,
    IconCursor,
    IconDatabase,
    IconDecisionTree,
    IconDownload,
    IconGear,
    IconGraph,
    IconLlmAnalytics,
    IconLogomark,
    IconMessage,
    IconNotification,
    IconPassword,
    IconPeople,
    IconPieChart,
    IconPlaylist,
    IconRevert,
    IconRewindPlay,
    IconSampling,
    IconSparkles,
    IconStack,
    IconTerminal,
    IconTestTube,
    IconToggle,
    IconUnlock,
    IconWarning,
} from '@posthog/icons'
import { LemonBanner, LemonButton, LemonCard, LemonLabel, LemonSelect, LemonTextArea, Link } from '@posthog/lemon-ui'

import { Logomark } from 'lib/brand/Logomark'
import {
    BuilderHog1,
    DetectiveHog,
    ExperimentsHog,
    ExplorerHog,
    FeatureFlagHog,
    FilmCameraHog,
    GraphsHog,
    MailHog,
    MicrophoneHog,
    RobotHog,
} from 'lib/components/hedgehogs'
import { useFeatureFlag } from 'lib/hooks/useFeatureFlag'
import { getFeatureFlagPayload } from 'lib/logic/featureFlagLogic'
import { inviteLogic } from 'scenes/settings/organization/inviteLogic'

import { ProductKey } from '~/queries/schema/schema-general'

import { UseCaseDefinition } from '../productRecommendations'
import { availableOnboardingProducts } from '../utils'
import { productSelectionLogic } from './productSelectionLogic'

const ICON_MAP: Record<string, React.ComponentType<{ className?: string; color?: string }>> = {
    IconBolt,
    IconBuilding,
    IconClock,
    IconCursor,
    IconDatabase,
    IconDecisionTree,
    IconDownload,
    IconGear,
    IconGraph,
    IconLlmAnalytics,
    IconLogomark,
    IconMessage,
    IconNotification,
    IconPassword,
    IconPeople,
    IconPieChart,
    IconPlaylist,
    IconRevert,
    IconRewindPlay,
    IconSampling,
    IconStack,
    IconTerminal,
    IconTestTube,
    IconToggle,
    IconUnlock,
    IconWarning,
}

type AvailableOnboardingProductKey = keyof typeof availableOnboardingProducts

const isAvailableOnboardingProductKey = (key: string | ProductKey): key is AvailableOnboardingProductKey =>
    key in availableOnboardingProducts

export function getProductIcon(
    iconKey?: string | null,
    { iconColor, className }: { iconColor?: string; className?: string } = {}
): JSX.Element {
    const IconComponent = iconKey ? ICON_MAP[iconKey] : undefined
    if (IconComponent) {
        return <IconComponent className={className} color={iconColor} />
    }

    return <IconLogomark className={className} />
}

function BrowsingHistoryBanner(): JSX.Element | null {
    const { hasBrowsingHistory, browsingHistoryLabels } = useValues(productSelectionLogic)

    if (!hasBrowsingHistory) {
        return null
    }

    return (
        <LemonBanner type="info" className="mb-6">
            Based on the documentation you browsed on our website ({browsingHistoryLabels.slice(0, 3).join(', ')}),
            we've tailored recommendations to your interests.
        </LemonBanner>
    )
}

function ChoosePathStep(): JSX.Element {
    const {
        useCases,
        aiDescription,
        aiRecommendationLoading,
        aiRecommendationError,
        hasBrowsingHistory,
        browsingHistoryLabels,
    } = useValues(productSelectionLogic)
    const { selectUseCase, setAiDescription, submitAiRecommendation, selectPickMyself } =
        useActions(productSelectionLogic)

    const aiRecommendationsEnabled = useFeatureFlag('ONBOARDING_AI_PRODUCT_RECOMMENDATIONS', 'test')
    const headingCopy = getFeatureFlagPayload('onboarding-product-selection-heading') as
        | { heading?: string; subheading?: string }
        | undefined
    const heading = headingCopy?.heading ?? 'What do you want to do with PostHog?'
    const defaultSubheading = aiRecommendationsEnabled
        ? "Describe your goals and we'll recommend the right products for you"
        : 'Pick a goal to get started with the right products'
    const subheading = headingCopy?.subheading ?? defaultSubheading

    return (
        <div className="max-w-6xl w-full">
            <div className="flex justify-center mb-4">
                <Logomark />
            </div>
            <h1 className="text-4xl font-bold text-center mb-2">{heading}</h1>
            <p className="text-center text-muted mb-8">{subheading}</p>

            {/* AI Input - Full width and prominent (behind feature flag) */}
            {aiRecommendationsEnabled && (
                <>
                    <div className="mb-8">
                        <LemonTextArea
                            placeholder="e.g., I want to understand why users drop off during checkout and run experiments to improve conversion..."
                            value={aiDescription}
                            onChange={(value) => setAiDescription(value)}
                            onPressEnter={() => {
                                if (aiDescription.trim()) {
                                    submitAiRecommendation()
                                }
                            }}
                            rows={3}
                        />
                        <div className="flex items-center justify-between mt-3">
                            <p className="text-muted text-xs mb-0">
                                {hasBrowsingHistory && (
                                    <>
                                        We'll also consider your interest in{' '}
                                        <em>{browsingHistoryLabels.slice(0, 2).join(' and ')}</em> based on your docs
                                        browsing history.
                                    </>
                                )}
                            </p>
                            <LemonButton
                                type="primary"
                                onClick={() => submitAiRecommendation()}
                                loading={aiRecommendationLoading}
                                disabledReason={
                                    !aiDescription.trim() ? 'Please describe what you want to achieve' : undefined
                                }
                                icon={<IconSparkles />}
                                data-attr="ai-recommend-products"
                            >
                                Get recommendations
                            </LemonButton>
                        </div>
                    </div>

                    {/* Error banner */}
                    {aiRecommendationError && (
                        <LemonBanner type="error" className="mb-4">
                            Failed to get recommendations. Please try again or pick a goal below.
                        </LemonBanner>
                    )}

                    {/* Divider */}
                    <div className="flex items-center gap-4 mb-8">
                        <div className="flex-1 border-t border-border" />
                        <span className="text-muted text-sm">or pick a common goal</span>
                        <div className="flex-1 border-t border-border" />
                    </div>
                </>
            )}

            {/* Use cases grid - 2 rows x 3 columns */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {useCases.map((useCase: UseCaseDefinition) => (
                    <LemonCard
                        key={useCase.key}
                        className={clsx(
                            'p-4',
                            aiRecommendationLoading ? 'opacity-50 pointer-events-none' : 'cursor-pointer'
                        )}
                        onClick={() => !aiRecommendationLoading && selectUseCase(useCase.key)}
                        hoverEffect={!aiRecommendationLoading}
                        data-attr={`use-case-${useCase.key}`}
                    >
                        <div className="flex flex-col items-center text-center gap-3">
                            <div className="text-3xl">
                                {getProductIcon(useCase.iconKey, {
                                    iconColor: useCase.iconColor,
                                    className: 'text-3xl',
                                })}
                            </div>
                            <div>
                                <div className="font-semibold mb-1">{useCase.title}</div>
                                <p className="text-muted text-sm mb-0">{useCase.description}</p>
                            </div>
                        </div>
                    </LemonCard>
                ))}

                {/* Pick myself option */}
                <LemonCard
                    className={clsx(
                        'p-4',
                        aiRecommendationLoading ? 'opacity-50 pointer-events-none' : 'cursor-pointer'
                    )}
                    onClick={() => !aiRecommendationLoading && selectPickMyself()}
                    hoverEffect={!aiRecommendationLoading}
                    data-attr="pick-myself-card"
                >
                    <div className="flex flex-col items-center text-center gap-3">
                        <div className="text-3xl">
                            <IconCursor className="text-3xl" color="rgb(100, 116, 139)" />
                        </div>
                        <div>
                            <div className="font-semibold mb-1">I'll pick myself</div>
                            <p className="text-muted text-sm mb-0">I know exactly which products I need</p>
                        </div>
                    </div>
                </LemonCard>
            </div>
        </div>
    )
}

const PRODUCT_HEDGEHOG: Partial<Record<string, React.ComponentType<{ className?: string }>>> = {
    [ProductKey.PRODUCT_ANALYTICS]: GraphsHog,
    [ProductKey.WEB_ANALYTICS]: ExplorerHog,
    [ProductKey.SESSION_REPLAY]: FilmCameraHog,
    [ProductKey.LLM_ANALYTICS]: RobotHog,
    [ProductKey.DATA_WAREHOUSE]: BuilderHog1,
    [ProductKey.FEATURE_FLAGS]: FeatureFlagHog,
    [ProductKey.EXPERIMENTS]: ExperimentsHog,
    [ProductKey.ERROR_TRACKING]: DetectiveHog,
    [ProductKey.SURVEYS]: MicrophoneHog,
    [ProductKey.WORKFLOWS]: MailHog,
}

function toSentenceCase(name: string): string {
    return name
        .split(' ')
        .map((word, i) => {
            if (i === 0) {
                return word
            }
            // Preserve acronyms (e.g. "LLM")
            if (word === word.toUpperCase() && word.length <= 4) {
                return word
            }
            return word.toLowerCase()
        })
        .join(' ')
}

function ProductCard({
    productKey,
    selected,
    onToggle,
}: {
    productKey: AvailableOnboardingProductKey
    selected: boolean
    onToggle: () => void
}): JSX.Element {
    const product = availableOnboardingProducts[productKey]

    return (
        <LemonCard
            data-attr={`${productKey}-onboarding-card`}
            className="relative cursor-pointer hover:transform-none p-4"
            onClick={onToggle}
            focused={selected}
            hoverEffect
        >
            <div className="flex flex-col items-center text-center gap-2">
                <div className="text-3xl">
                    {getProductIcon(product.icon, {
                        iconColor: product.iconColor,
                        className: 'text-3xl',
                    })}
                </div>
                <div>
                    <h3 className="font-semibold mb-1 text-sm">{product.name}</h3>
                    <p className="text-muted text-xs mb-0">{product.description}</p>
                </div>
            </div>
        </LemonCard>
    )
}

function ProductSelectionStep(): JSX.Element {
    const {
        selectedProducts,
        firstProductOnboarding,
        recommendedProducts,
        otherProducts,
        showAllProducts,
        canContinue,
        recommendationSourceLabel,
        aiRecommendation,
        recommendationSource,
    } = useValues(productSelectionLogic)
    const { toggleProduct, setFirstProductOnboarding, handleStartOnboarding, setShowAllProducts, setStep } =
        useActions(productSelectionLogic)
    const { showInviteModal } = useActions(inviteLogic)

    const availableRecommendedProducts = recommendedProducts.filter(isAvailableOnboardingProductKey)
    const availableOtherProducts = otherProducts.filter(isAvailableOnboardingProductKey)

    return (
        <div className="max-w-6xl w-full">
            <div className="flex justify-center mb-4">
                <Logomark />
            </div>
            <h1 className="text-4xl font-bold text-center mb-2">Which products would you like to use?</h1>
            <p className="text-center text-muted mb-8">
                {recommendationSourceLabel ? (
                    <>We've pre-selected some products {recommendationSourceLabel}. Feel free to change or add more.</>
                ) : (
                    <>Select all that apply — you can pick more than one!</>
                )}
            </p>

            {/* AI reasoning banner */}
            {recommendationSource === 'ai' && aiRecommendation?.reasoning && (
                <LemonBanner type="ai" className="mb-6">
                    {aiRecommendation.reasoning}
                </LemonBanner>
            )}

            {/* Browsing history banner */}
            {recommendationSource === 'browsing_history' && <BrowsingHistoryBanner />}

            {/* Products list - single unified grid */}
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3 justify-items-center w-full">
                {/* Recommended products first */}
                {availableRecommendedProducts.map((productKey) => (
                    <ProductCard
                        key={productKey}
                        productKey={productKey}
                        selected={selectedProducts.includes(productKey)}
                        onToggle={() => toggleProduct(productKey)}
                    />
                ))}

                {/* Other products - shown/hidden based on toggle */}
                {availableOtherProducts.length > 0 &&
                    showAllProducts &&
                    availableOtherProducts.map((productKey) => (
                        <ProductCard
                            key={productKey}
                            productKey={productKey}
                            selected={selectedProducts.includes(productKey)}
                            onToggle={() => toggleProduct(productKey)}
                        />
                    ))}
            </div>

            {/* Show more toggle - only show when collapsed */}
            {availableOtherProducts.length > 0 && availableRecommendedProducts.length > 0 && !showAllProducts && (
                <div className="flex justify-center mt-4">
                    <button
                        onClick={() => setShowAllProducts(true)}
                        className="text-muted hover:text-default text-sm flex items-center gap-1 cursor-pointer"
                    >
                        Show all products ({availableOtherProducts.length} more) <IconChevronDown className="text-xs" />
                    </button>
                </div>
            )}

            {/* Continue button */}
            <div className="flex flex-col items-center gap-4 mt-8">
                {selectedProducts.length > 1 ? (
                    <div className="flex gap-2 items-center justify-center">
                        <LemonLabel>Start with</LemonLabel>
                        <LemonSelect
                            value={firstProductOnboarding}
                            options={selectedProducts.filter(isAvailableOnboardingProductKey).map((productKey) => ({
                                label: availableOnboardingProducts[productKey].name,
                                value: productKey,
                            }))}
                            onChange={(value) => value && setFirstProductOnboarding(value)}
                            placeholder="Select a product"
                            className="bg-surface-primary"
                        />
                        <LemonButton
                            sideIcon={<IconArrowRight />}
                            onClick={handleStartOnboarding}
                            type="primary"
                            status="alt"
                            data-attr="onboarding-continue"
                        >
                            Go
                        </LemonButton>
                    </div>
                ) : (
                    <LemonButton
                        type="primary"
                        status="alt"
                        onClick={handleStartOnboarding}
                        data-attr="onboarding-continue"
                        sideIcon={<IconArrowRight />}
                        disabledReason={!canContinue ? 'Select at least one product to continue' : undefined}
                    >
                        Get started
                    </LemonButton>
                )}
                <button
                    className="text-muted hover:text-default text-sm cursor-pointer"
                    onClick={() => setStep('choose_path')}
                >
                    ← Go back
                </button>
            </div>

            <p className="text-center mt-8 text-muted">
                Need help from a team member? <Link onClick={() => showInviteModal()}>Invite them</Link>
            </p>
        </div>
    )
}

function SimplifiedProductSelection(): JSX.Element {
    const { firstProductOnboarding, hasBrowsingHistory } = useValues(productSelectionLogic)
    const { setFirstProductOnboarding, selectSingleProduct } = useActions(productSelectionLogic)
    const { showInviteModal } = useActions(inviteLogic)

    const allProducts = Object.keys(availableOnboardingProducts) as AvailableOnboardingProductKey[]

    // Pre-select: browsing history suggestion if available, otherwise first product
    const initialIndex = firstProductOnboarding
        ? Math.max(0, allProducts.indexOf(firstProductOnboarding as AvailableOnboardingProductKey))
        : 0

    const [activeIndex, setActiveIndex] = useState<number>(initialIndex)
    const [transitioning, setTransitioning] = useState(false)
    const [slideDirection, setSlideDirection] = useState<'left' | 'right'>('right')
    const [mounted, setMounted] = useState(false)

    useEffect(() => {
        const timer = setTimeout(() => setMounted(true), 100)
        return () => clearTimeout(timer)
    }, [])

    const spotlightKey = allProducts[activeIndex]
    const spotlightProduct = availableOnboardingProducts[spotlightKey]
    const spotlightDescription = spotlightProduct.userCentricDescription || spotlightProduct.description
    const HedgehogComponent = PRODUCT_HEDGEHOG[spotlightKey]

    const navigateTo = useCallback(
        (newIndex: number, direction: 'left' | 'right'): void => {
            const productKey = allProducts[newIndex]
            setSlideDirection(direction)
            setTransitioning(true)
            setTimeout(() => {
                setActiveIndex(newIndex)
                setFirstProductOnboarding(productKey)
                setTransitioning(false)
            }, 200)
        },
        [allProducts, setFirstProductOnboarding]
    )

    const handlePickProduct = (productKey: AvailableOnboardingProductKey): void => {
        const newIndex = allProducts.indexOf(productKey)
        const direction = getWrappedOffset(newIndex) > 0 ? 'right' : 'left'
        navigateTo(newIndex, direction)
    }

    const handlePrev = (): void => {
        navigateTo((activeIndex - 1 + allProducts.length) % allProducts.length, 'left')
    }

    const handleNext = (): void => {
        navigateTo((activeIndex + 1) % allProducts.length, 'right')
    }

    const handleGetStarted = (): void => {
        selectSingleProduct(spotlightKey)
    }

    useEffect(() => {
        const onKeyDown = (e: KeyboardEvent): void => {
            if (e.key === 'ArrowLeft') {
                e.preventDefault()
                handlePrev()
            } else if (e.key === 'ArrowRight') {
                e.preventDefault()
                handleNext()
            } else if (e.key === 'Enter') {
                e.preventDefault()
                handleGetStarted()
            }
        }
        window.addEventListener('keydown', onKeyDown)
        return () => window.removeEventListener('keydown', onKeyDown)
    })

    const getWrappedOffset = (itemIndex: number): number => {
        let offset = itemIndex - activeIndex
        const half = allProducts.length / 2
        if (offset > half) {
            offset -= allProducts.length
        }
        if (offset < -half) {
            offset += allProducts.length
        }
        return offset
    }

    return (
        <div className="flex flex-col flex-1 w-full min-h-full p-4 items-center justify-center bg-primary overflow-x-hidden">
            <div className="flex flex-col items-center justify-center flex-grow w-full max-w-2xl">
                <div className="flex justify-center mb-3">
                    <Logomark />
                </div>
                <h1 className="text-4xl font-bold text-center mb-1">What's your first priority?</h1>
                <p className="text-center text-muted mb-6">
                    {hasBrowsingHistory
                        ? 'Based on your browsing, we picked a great place to start.'
                        : 'Pick one to start — you can always add more later.'}
                </p>

                {/* Spotlight card with navigation chevrons */}
                <div className="flex items-center gap-3 w-full max-w-2xl mb-8">
                    <button
                        onClick={handlePrev}
                        className="shrink-0 p-2 rounded-full hover:bg-surface-primary text-muted hover:text-default transition-colors cursor-pointer"
                        aria-label="Previous product"
                    >
                        <IconChevronLeft className="text-2xl" />
                    </button>
                    <div className="flex-1 max-w-xl mx-auto rounded-lg border overflow-hidden bg-surface-primary">
                        <div
                            className="h-1 transition-all duration-500"
                            style={{ backgroundColor: spotlightProduct.iconColor }}
                        />
                        <div
                            className="flex h-[256px] transition-all duration-200"
                            style={{
                                opacity: transitioning ? 0 : 1,
                                transform: transitioning
                                    ? `translateX(${slideDirection === 'right' ? '-12px' : '12px'})`
                                    : 'translateX(0)',
                            }}
                        >
                            <div className="w-[140px] shrink-0 relative overflow-hidden flex items-end justify-center">
                                <div
                                    className="absolute inset-0 opacity-[0.15]"
                                    style={{ backgroundColor: spotlightProduct.iconColor }}
                                />
                                {HedgehogComponent && (
                                    <HedgehogComponent className="relative z-10 w-[110px] h-[110px] object-contain mb-1" />
                                )}
                            </div>
                            <div className="flex-1 flex flex-col justify-between p-5">
                                <div>
                                    <div className="flex items-center gap-1.5 text-xs text-muted mb-1.5">
                                        {getProductIcon(spotlightProduct.icon, {
                                            iconColor: spotlightProduct.iconColor,
                                            className: 'text-sm',
                                        })}
                                        <span>{toSentenceCase(spotlightProduct.name)}</span>
                                    </div>
                                    <h2 className="text-xl font-bold mb-2">{spotlightDescription}</h2>
                                    {spotlightProduct.capabilities && (
                                        <ul className="list-none p-0 m-0 flex flex-col gap-1">
                                            {spotlightProduct.capabilities.map((cap) => (
                                                <li key={cap} className="text-sm text-muted flex items-center gap-2">
                                                    <span
                                                        className="w-1 h-1 rounded-full shrink-0"
                                                        style={{
                                                            backgroundColor: spotlightProduct.iconColor,
                                                        }}
                                                    />
                                                    {cap}
                                                </li>
                                            ))}
                                        </ul>
                                    )}
                                </div>
                                <LemonButton
                                    type="primary"
                                    status="alt"
                                    size="large"
                                    onClick={handleGetStarted}
                                    sideIcon={<IconArrowRight />}
                                    data-attr="onboarding-continue"
                                >
                                    Start with {toSentenceCase(spotlightProduct.name)}
                                </LemonButton>
                            </div>
                        </div>
                    </div>
                    <button
                        onClick={handleNext}
                        className="shrink-0 p-2 rounded-full hover:bg-surface-primary text-muted hover:text-default transition-colors cursor-pointer"
                        aria-label="Next product"
                    >
                        <IconChevronRight className="text-2xl" />
                    </button>
                </div>

                {/* Arc wheel carousel */}
                <div className="relative w-full h-[130px] mb-4">
                    {allProducts.map((productKey, index) => {
                        const product = availableOnboardingProducts[productKey]
                        const offset = getWrappedOffset(index)
                        const absOffset = Math.abs(offset)
                        const isActive = index === activeIndex
                        const isVisible = absOffset <= 5

                        const x = offset * 100
                        const y = absOffset * absOffset * 3
                        const scale = Math.max(0.65, 1 - absOffset * 0.06)
                        const itemOpacity = isVisible ? Math.max(0.3, 1 - absOffset * 0.15) : 0

                        const entranceDelay = absOffset * 60

                        return (
                            <button
                                key={productKey}
                                onClick={() => isVisible && handlePickProduct(productKey)}
                                className={clsx(
                                    'absolute left-1/2 flex flex-col items-center gap-1 transition-all duration-500 ease-in-out',
                                    isVisible ? 'cursor-pointer' : 'pointer-events-none'
                                )}
                                style={{
                                    transform: mounted
                                        ? `translateX(calc(-50% + ${x}px)) translateY(${y}px) scale(${scale})`
                                        : `translateX(-50%) translateY(30px) scale(0.8)`,
                                    opacity: mounted ? itemOpacity : 0,
                                    zIndex: 10 - absOffset,
                                    transitionDelay: !mounted ? `${entranceDelay}ms` : '0ms',
                                }}
                                data-attr={`${productKey}-arc-item`}
                            >
                                <div
                                    className={clsx(
                                        'rounded-xl p-2.5 transition-all duration-300',
                                        isActive
                                            ? 'border-2 border-accent shadow-md bg-surface-primary'
                                            : 'border border-primary bg-surface-primary'
                                    )}
                                >
                                    {getProductIcon(product.icon, {
                                        iconColor: product.iconColor,
                                        className: 'text-2xl',
                                    })}
                                </div>
                                <span
                                    className={clsx(
                                        'text-xs whitespace-nowrap transition-all duration-300',
                                        isActive ? 'text-default font-medium' : 'text-muted',
                                        absOffset > 2 && 'opacity-0'
                                    )}
                                >
                                    {toSentenceCase(product.name)}
                                </span>
                            </button>
                        )
                    })}
                </div>

                <div className="flex items-center gap-4 text-muted text-xs mb-3">
                    <span className="flex items-center gap-1.5">
                        <kbd className="px-1.5 py-0.5 rounded border border-primary bg-surface-primary text-[10px] font-mono">
                            &larr;
                        </kbd>
                        <kbd className="px-1.5 py-0.5 rounded border border-primary bg-surface-primary text-[10px] font-mono">
                            &rarr;
                        </kbd>
                        browse
                    </span>
                    <span className="flex items-center gap-1.5">
                        <kbd className="px-1.5 py-0.5 rounded border border-primary bg-surface-primary text-[10px] font-mono">
                            &crarr;
                        </kbd>
                        select
                    </span>
                </div>
                <p className="text-muted text-xs mb-2">You can add more products anytime from Settings.</p>
                <p className="text-muted text-sm">
                    Need help from a team member? <Link onClick={() => showInviteModal()}>Invite them</Link>
                </p>
            </div>
        </div>
    )
}

export function ProductSelection(): JSX.Element {
    const simplified = useFeatureFlag('ONBOARDING_SIMPLIFIED_PRODUCT_SELECTION')
    const { currentStep } = useValues(productSelectionLogic)

    if (simplified) {
        return <SimplifiedProductSelection />
    }

    return (
        <div className="flex flex-col flex-1 w-full min-h-full p-4 items-center justify-center bg-primary overflow-x-hidden">
            <div className="flex flex-col items-center justify-center flex-grow w-full">
                {currentStep === 'choose_path' && <ChoosePathStep />}
                {currentStep === 'product_selection' && <ProductSelectionStep />}
            </div>
        </div>
    )
}

export default ProductSelection
